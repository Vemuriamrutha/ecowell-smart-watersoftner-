"""
storage.py — Thread-safe in-memory store for telemetry, events, and alerts.
Acts as the backend's live database between MQTT messages and REST API calls.
"""

from threading import Lock
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:

    def __init__(self):
        self.lock      = Lock()
        self.telemetry = {}
        self.events    = []       # last 200 events (newest at end)
        self.alerts    = []       # active unresolved alerts

    # ── TELEMETRY ──────────────────────────────────────────────────────────

    def update_telemetry(self, data: dict):
        with self.lock:
            self.telemetry = data
            # Auto-derive alerts from telemetry
            self._refresh_alerts(data)

    def get_telemetry(self) -> dict:
        with self.lock:
            return dict(self.telemetry)

    # ── EVENTS ─────────────────────────────────────────────────────────────

    def add_event(self, event: dict):
        with self.lock:
            self.events.append(event)
            if len(self.events) > 200:
                self.events.pop(0)

    def get_events(self) -> list:
        with self.lock:
            return list(self.events)

    # ── ALERTS (derived from latest telemetry) ────────────────────────────

    def _refresh_alerts(self, data: dict):
        """Rebuild the active-alert list from the latest telemetry snapshot."""
        alerts = []
        sensors = data.get("sensors", {})
        state   = data.get("state", "")

        if sensors.get("salt_level_pct", 100) <= 15:
            alerts.append({
                "id": "LOW_SALT", "level": "ALERT",
                "message": f"Salt level critical: {sensors['salt_level_pct']:.1f}%",
                "time": _now(),
            })
        elif sensors.get("salt_level_pct", 100) <= 25:
            alerts.append({
                "id": "SALT_WARN", "level": "WARN",
                "message": f"Salt level low: {sensors['salt_level_pct']:.1f}% — refill soon",
                "time": _now(),
            })

        if sensors.get("tds_ppm", 0) >= 500:
            alerts.append({
                "id": "HIGH_TDS", "level": "ALERT",
                "message": f"TDS high: {sensors['tds_ppm']} ppm — water quality poor",
                "time": _now(),
            })

        if sensors.get("water_pressure_bar", 5) < 1.0:
            alerts.append({
                "id": "LOW_PRESSURE", "level": "ALERT",
                "message": f"Low pressure: {sensors['water_pressure_bar']} bar",
                "time": _now(),
            })

        if not sensors.get("power_status", True):
            alerts.append({
                "id": "POWER_FAIL", "level": "FAULT",
                "message": "Power failure detected",
                "time": _now(),
            })

        if state == "FAULT":
            alerts.append({
                "id": "FAULT", "level": "FAULT",
                "message": f"Device in FAULT: {data.get('fault_reason', 'Unknown')}",
                "time": _now(),
            })

        self.alerts = alerts

    def get_alerts(self) -> list:
        with self.lock:
            return list(self.alerts)

    # ── DEVICE HEALTH SCORE ───────────────────────────────────────────────

    def get_health_score(self) -> dict:
        """
        Compute a 0-100 device health score from latest sensor values.
        Used to give field technicians a quick snapshot.
        """
        with self.lock:
            data    = self.telemetry
            sensors = data.get("sensors", {})
            state   = data.get("state", "")

        if not sensors:
            return {"score": None, "grade": "N/A", "factors": []}

        score   = 100
        factors = []

        # Salt deduction
        salt = sensors.get("salt_level_pct", 100)
        if salt <= 15:
            score -= 35; factors.append(f"Salt critical ({salt:.0f}%)")
        elif salt <= 30:
            score -= 20; factors.append(f"Salt low ({salt:.0f}%)")
        elif salt <= 50:
            score -= 8;  factors.append(f"Salt moderate ({salt:.0f}%)")

        # TDS deduction
        tds = sensors.get("tds_ppm", 150)
        if tds >= 500:
            score -= 25; factors.append(f"TDS high ({tds:.0f} ppm)")
        elif tds >= 350:
            score -= 12; factors.append(f"TDS elevated ({tds:.0f} ppm)")

        # Pressure deduction
        pressure = sensors.get("water_pressure_bar", 3)
        if pressure < 1.0:
            score -= 20; factors.append(f"Pressure critical ({pressure} bar)")
        elif pressure < 1.5:
            score -= 10; factors.append(f"Pressure low ({pressure} bar)")

        # Fault deduction
        if state == "FAULT":
            score -= 30; factors.append("Device in FAULT state")

        # Power
        if not sensors.get("power_status", True):
            score -= 20; factors.append("Power failure")

        score = max(0, min(100, score))

        if score >= 85:
            grade = "Excellent"
        elif score >= 70:
            grade = "Good"
        elif score >= 50:
            grade = "Fair"
        elif score >= 30:
            grade = "Poor"
        else:
            grade = "Critical"

        return {"score": score, "grade": grade, "factors": factors}


# Global singleton
storage = Storage()