"""
state_machine.py — EcoWell Device State Machine
Handles all state transitions, regeneration timing, and fault detection.
"""

from enum import Enum
from sensors import SALT_CRITICAL_PCT, PRESSURE_MIN_BAR, TDS_HIGH_PPM

# ── States ────────────────────────────────────────────────────────────────────

class State(str, Enum):
    IDLE                  = "IDLE"
    MONITORING            = "MONITORING"
    REGENERATION_REQUIRED = "REGENERATION_REQUIRED"
    REGENERATION_RUNNING  = "REGENERATION_RUNNING"
    FAULT                 = "FAULT"


# ── Timing (seconds) ──────────────────────────────────────────────────────────
REGEN_DURATION_SEC = 15    # how long a successful cycle takes
REGEN_TIMEOUT_SEC  = 25    # watchdog — fault if not completed by this time

# ── State Machine ─────────────────────────────────────────────────────────────

class StateMachine:

    def __init__(self):
        self.state              = State.IDLE
        self.fault_reason       = None
        self.regen_start_time   = None
        self.force_regen_fail   = False
        self.last_regen_result  = None   # "completed" | "failed" | None
        self._power_was_on      = True   # for edge-detect on power failure

    def evaluate(self, sensors, current_time):
        """
        Evaluate sensor values and advance the state machine.
        Returns list of (message, level) event tuples.
        """
        events         = []
        previous_state = self.state

        # ──────────────────────────────────────────────────────────────────────
        # POWER FAILURE — highest priority check
        # ──────────────────────────────────────────────────────────────────────
        if not sensors.power_status:
            if self._power_was_on:                   # edge detect — first tick after failure
                self._power_was_on  = False
                self.fault_reason   = "Power failure detected"
                self.state          = State.FAULT
                events.append(("Power failure detected — device entered FAULT state", "FAULT"))
            return self._finalise(events, previous_state)

        # ──────────────────────────────────────────────────────────────────────
        # POWER RESTORED
        # ──────────────────────────────────────────────────────────────────────
        if not self._power_was_on and sensors.power_status:
            self._power_was_on = True
            self.fault_reason  = None
            self.state         = State.MONITORING
            events.append(("Power restored — resuming MONITORING", "INFO"))
            return self._finalise(events, previous_state)

        # ──────────────────────────────────────────────────────────────────────
        # IDLE → MONITORING (boot transition)
        # ──────────────────────────────────────────────────────────────────────
        if self.state == State.IDLE:
            self.state = State.MONITORING
            events.append(("Device powered up — entering MONITORING state", "INFO"))
            return self._finalise(events, previous_state)

        # ──────────────────────────────────────────────────────────────────────
        # MONITORING — check conditions
        # ──────────────────────────────────────────────────────────────────────
        if self.state == State.MONITORING:

            # Low pressure → FAULT (cannot safely operate)
            if sensors.water_pressure < PRESSURE_MIN_BAR:
                self.fault_reason = f"Low water pressure ({sensors.water_pressure} bar)"
                self.state        = State.FAULT
                events.append((f"Low water pressure detected: {sensors.water_pressure} bar — FAULT", "FAULT"))

            # Salt critical → REGENERATION_REQUIRED
            elif sensors.salt_level <= SALT_CRITICAL_PCT:
                events.append((f"Salt critically low ({sensors.salt_level:.1f}%) — regeneration required", "ALERT"))
                self.state = State.REGENERATION_REQUIRED

            # High TDS → REGENERATION_REQUIRED
            elif sensors.tds >= TDS_HIGH_PPM:
                events.append((f"TDS high ({sensors.tds:.0f} ppm) — water quality poor, regeneration required", "ALERT"))
                self.state = State.REGENERATION_REQUIRED

        # ──────────────────────────────────────────────────────────────────────
        # REGENERATION_REQUIRED — waiting for operator command
        # ──────────────────────────────────────────────────────────────────────
        elif self.state == State.REGENERATION_REQUIRED:
            # Stay here until regeneration is triggered or condition clears
            # (if somehow salt/TDS improves, go back to MONITORING)
            if sensors.salt_level > SALT_CRITICAL_PCT and sensors.tds < TDS_HIGH_PPM:
                self.state = State.MONITORING
                events.append(("Conditions improved — returning to MONITORING", "INFO"))

        # ──────────────────────────────────────────────────────────────────────
        # REGENERATION_RUNNING — watch cycle progress
        # ──────────────────────────────────────────────────────────────────────
        elif self.state == State.REGENERATION_RUNNING:
            elapsed = current_time - self.regen_start_time

            if self.force_regen_fail:
                # Forced failure (debug)
                self.force_regen_fail  = False
                self.fault_reason      = "Regeneration failed (forced debug failure)"
                self.last_regen_result = "failed"
                self.state             = State.FAULT
                events.append(("Regeneration failed — device entered FAULT state", "FAULT"))

            elif elapsed >= REGEN_TIMEOUT_SEC:
                # Watchdog timeout
                self.fault_reason      = f"Regeneration timeout after {REGEN_TIMEOUT_SEC}s"
                self.last_regen_result = "failed"
                self.state             = State.FAULT
                events.append((f"Regeneration timed out ({REGEN_TIMEOUT_SEC}s) — FAULT", "FAULT"))

            elif elapsed >= REGEN_DURATION_SEC:
                # Success — restore sensor levels
                sensors.salt_level     = 90.0
                sensors.tds            = 150.0
                self.last_regen_result = "completed"
                self.state             = State.MONITORING
                events.append((f"Regeneration completed successfully in {elapsed:.0f}s", "INFO"))

        # ──────────────────────────────────────────────────────────────────────
        # FAULT — stays here until manually recovered via reset_debug or power cycle
        # ──────────────────────────────────────────────────────────────────────
        # (no auto-recovery from non-power faults)

        return self._finalise(events, previous_state)

    def _finalise(self, events, previous_state):
        """Append a state-change event if the state transitioned."""
        if previous_state != self.state:
            events.append((
                f"State transition: {previous_state.value} -> {self.state.value}",
                "INFO",
            ))
        return events

    def start_regeneration(self, current_time):
        """Called by Device after safety checks pass."""
        self.state           = State.REGENERATION_RUNNING
        self.regen_start_time = current_time
        self.last_regen_result = None