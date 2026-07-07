"""
simulator.py — EcoWell Smart Water Softener Device Simulator
Simulates a physical IoT device: reads sensors, runs state machine,
publishes telemetry + events via MQTT, handles remote commands.
"""

import time
import threading
import config
import mqtt_client
import persistance
from sensors import SensorModel
from state_machine import StateMachine, State
from safety import can_start_regeneration
from events import EventLog


class Device:
    def __init__(self, client):
        self.client = client
        self.lock   = threading.Lock()
        self.sensors = SensorModel()
        self.fsm     = StateMachine()
        self.log     = EventLog()

        # Restore previous state on power-on
        previous = persistance.load_state()
        if previous:
            prev_state = previous.get("state", "IDLE")
            self.log.add(f"Power-on: resumed from previous state {prev_state}", "INFO")
            print(f"[Device] Resumed from: {prev_state}")
        else:
            self.log.add("Power-on: fresh start", "INFO")

        # Predictive alert tracking (salt refill predictor)
        self._salt_samples      = []
        self._last_salt_warn    = 0     # prevent spam
        self._last_no_flow_warn = 0

    # ── Event publishing ─────────────────────────────────────────────

    def publish_event(self, message, level):
        entry = self.log.add(message, level)
        print(f"[{entry['time']}] [{level:5s}] {message}")
        mqtt_client.publish_json(self.client, config.MQTT_EVENT_TOPIC, entry)

    # ── Telemetry publishing ─────────────────────────────────────────

    def publish_telemetry(self):
        s = self.sensors
        payload = {
            "device_id":   config.DEVICE_ID,
            "time":        self.log.entries[-1]["time"] if self.log.entries else None,
            "state":       self.fsm.state.value,
            "fault_reason": self.fsm.fault_reason,
            "sensors": s.as_dict(),
            "regen_status": (
                "RUNNING"    if self.fsm.state == State.REGENERATION_RUNNING else
                "COMPLETED"  if self.fsm.last_regen_result == "completed"     else
                "FAILED"     if self.fsm.last_regen_result == "failed"        else
                "NONE"
            ),
            "health_hint": self._predictive_salt_eta(),
        }
        mqtt_client.publish_json(self.client, config.MQTT_TELEMETRY_TOPIC, payload)

    # ── Predictive salt depletion ─────────────────────────────────────

    def _predictive_salt_eta(self):
        """
        Estimate how many hours until salt hits the 15% critical mark,
        based on recent depletion rate. Returns a human-readable hint.
        """
        s = self.sensors.salt_level
        self._salt_samples.append(s)
        if len(self._salt_samples) > 30:
            self._salt_samples.pop(0)
        if len(self._salt_samples) < 5:
            return None

        # depletion per tick (2 s intervals) over the last samples
        rate = (self._salt_samples[0] - self._salt_samples[-1]) / len(self._salt_samples)
        if rate <= 0:
            return None
        ticks_to_critical = (s - 15) / rate
        hours = ticks_to_critical * config.SENSOR_UPDATE_INTERVAL / 3600
        if hours < 1:
            return "Salt critical in < 1 hour — refill now!"
        if hours < 24:
            return f"Salt refill needed in ~{hours:.0f} h"
        return f"Salt OK for ~{hours/24:.0f} day(s)"

    # ── Main simulation tick ─────────────────────────────────────────

    def tick(self):
        with self.lock:
            now = time.time()
            self.sensors.update(is_regenerating=(self.fsm.state == State.REGENERATION_RUNNING))

            # Run state machine
            events = self.fsm.evaluate(self.sensors, now)
            for message, level in events:
                self.publish_event(message, level)

            # Predictive alerts (anti-spam: once per 60 s)
            self._check_predictive(now)

            # Persist + publish
            persistance.save_state(self.fsm.state.value, self.sensors.as_dict())
            self.publish_telemetry()
            
            # Print mock OLED display to console
            self._print_oled_display()

    def _print_oled_display(self):
        s = self.sensors
        state_str = self.fsm.state.value
        print("\n+----------------------------------------+")
        print(f"|  ECOWELL OLED DISPLAY (Local Monitor)  |")
        print("+----------------------------------------+")
        print(f"|  State:    {state_str:<26}  |")
        print(f"|  Flow:     {s.water_flow:<4.1f} L/min  TDS: {int(s.tds):<4d} ppm    |")
        print(f"|  Pressure: {s.water_pressure:<4.2f} bar  Salt: {s.salt_level:<4.1f}%    |")
        print(f"|  Power:    {'ONLINE' if s.power_status else 'OFFLINE':<27} |")
        print("+----------------------------------------+")

    def _check_predictive(self, now):
        s = self.sensors
        # Salt refill predictor — warn at 25% but not every 2 seconds
        if 15 < s.salt_level <= 25 and (now - self._last_salt_warn) > 60:
            self.publish_event(
                f"[Predictive] Salt level {s.salt_level:.1f}% — refill recommended soon", "ALERT"
            )
            self._last_salt_warn = now

        # No-flow warning (only in MONITORING, power on, non-regen)
        if (self.fsm.state == State.MONITORING
                and s.power_status
                and s.water_flow == 0
                and (now - self._last_no_flow_warn) > 30):
            self.publish_event("No water flow detected while system is active", "ALERT")
            self._last_no_flow_warn = now

    # ── Command handler ──────────────────────────────────────────────

    def handle_command(self, command):
        with self.lock:
            cmd = command.strip().lower()
            now = time.time()

            if cmd == "regenerate":
                ok, reason = can_start_regeneration(self.sensors, self.fsm.state)
                if ok:
                    self.fsm.start_regeneration(now)
                    self.publish_event("Remote regeneration command accepted — cycle started", "INFO")
                else:
                    self.publish_event(f"Regeneration REJECTED — {reason}", "ALERT")

            elif cmd == "force_low_salt":
                self.sensors.force_low_salt = not self.sensors.force_low_salt
                status = "forced" if self.sensors.force_low_salt else "cleared"
                self.publish_event(f"[DEBUG] Low salt condition {status}", "INFO")

            elif cmd == "force_low_pressure":
                self.sensors.force_low_pressure = not self.sensors.force_low_pressure
                status = "forced" if self.sensors.force_low_pressure else "cleared"
                self.publish_event(f"[DEBUG] Low pressure condition {status}", "INFO")

            elif cmd == "force_high_tds":
                self.sensors.force_high_tds = not self.sensors.force_high_tds
                status = "forced" if self.sensors.force_high_tds else "cleared"
                self.publish_event(f"[DEBUG] High TDS condition {status}", "INFO")

            elif cmd == "force_power_failure":
                self.sensors.force_power_failure = not self.sensors.force_power_failure
                status = "forced" if self.sensors.force_power_failure else "cleared"
                self.publish_event(f"[DEBUG] Power failure {status}", "INFO")

            elif cmd == "force_regen_fail":
                self.fsm.force_regen_fail = not self.fsm.force_regen_fail
                status = "forced" if self.fsm.force_regen_fail else "cleared"
                self.publish_event(f"[DEBUG] Next regeneration force-fail {status}", "INFO")

            elif cmd == "reset_debug":
                self.sensors.reset_debug_flags()
                self.fsm.force_regen_fail = False
                self.publish_event("[DEBUG] All debug conditions cleared", "INFO")

            elif cmd == "ota_update":
                self.publish_event("OTA update command received. Initializing firmware download...", "INFO")
                # Simulate a download progress bar in console
                def run_ota():
                    print("\n[OTA] Downloading firmware update v1.1.0...")
                    for i in range(1, 6):
                        time.sleep(1)
                        pct = i * 20
                        bar = "█" * i + "░" * (5 - i)
                        print(f"[OTA] [{bar}] {pct}% downloaded")
                    print("[OTA] Download complete. Verifying signature...")
                    time.sleep(1)
                    print("[OTA] Signature verified. Flashing partition 1...")
                    time.sleep(1)
                    print("[OTA] Flash success. Rebooting device...\n")
                    with self.lock:
                        self.fsm.state = State.MONITORING
                        self.sensors.reset_debug_flags()
                        self.publish_event("OTA firmware update complete. Rebooted successfully into v1.1.0", "INFO")
                
                import threading
                threading.Thread(target=run_ota, daemon=True).start()

            else:
                self.publish_event(f"Unknown command ignored: {command}", "ALERT")


# ── Global device instance ─────────────────────────────────────────

device = None


def telemetry_loop():
    while True:
        try:
            device.tick()
        except Exception as e:
            print(f"[Error] tick() failed: {e}")
        time.sleep(config.SENSOR_UPDATE_INTERVAL)


def debug_console():
    print("\n" + "="*60)
    print("  EcoWell Device Simulator — Debug Console")
    print("="*60)
    print("  Commands:")
    print("    regenerate          — trigger remote regeneration")
    print("    force_low_salt      — simulate salt depletion")
    print("    force_low_pressure  — simulate low pressure")
    print("    force_high_tds      — simulate poor water quality")
    print("    force_power_failure — simulate power outage")
    print("    force_regen_fail    — next regen cycle will fail")
    print("    reset_debug         — clear all forced conditions")
    print("    ota_update          — trigger mock over-the-air firmware update")
    print("="*60 + "\n")
    while True:
        try:
            cmd = input(">> ").strip()
            if cmd:
                device.handle_command(cmd)
        except (EOFError, KeyboardInterrupt):
            print("\n[Device] Simulator shutting down.")
            break


def main():
    global device
    print("[Device] Connecting to MQTT broker…")
    client = mqtt_client.create_client(
        client_id=f"ecowell-sim-{config.DEVICE_ID}",
        on_command_received=lambda cmd: device.handle_command(cmd),
    )
    device = Device(client)
    print(f"[Device] {config.DEVICE_ID} online — publishing to broker at {config.MQTT_BROKER}")

    t = threading.Thread(target=telemetry_loop, daemon=True)
    t.start()

    debug_console()


if __name__ == "__main__":
    main()
