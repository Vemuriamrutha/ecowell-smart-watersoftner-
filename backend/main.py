"""
backend/main.py — EcoWell IoT Backend (Flask version)
Single-server: handles MQTT subscription, REST API, and command dispatch.
Flask is simpler to run — no uvicorn needed: python main.py
"""

from flask import Flask, jsonify, request
import threading
import json
import paho.mqtt.client as mqtt
from datetime import datetime, timezone

# ── Storage ────────────────────────────────────────────────────────────────────

from threading import Lock

class Storage:
    def __init__(self):
        self.lock = Lock()
        self.telemetry = {}
        self.events = []
        self.alerts = []

    def update_telemetry(self, data):
        with self.lock:
            self.telemetry = data
            self._refresh_alerts(data)

    def get_telemetry(self):
        with self.lock:
            return dict(self.telemetry)

    def add_event(self, event):
        with self.lock:
            self.events.append(event)
            if len(self.events) > 200:
                self.events.pop(0)

    def get_events(self):
        with self.lock:
            return list(self.events)

    # Active alerts derived from telemetry
    def _refresh_alerts(self, data):
        alerts = []
        sensors = data.get("sensors", {})
        state   = data.get("state", "")
        def now():
            return datetime.now(timezone.utc).isoformat(timespec="seconds")

        salt = sensors.get("salt_level_pct", 100)
        if salt <= 15:
            alerts.append({"id": "LOW_SALT",  "level": "ALERT", "message": f"Salt critically low: {salt:.1f}%", "time": now()})
        elif salt <= 25:
            alerts.append({"id": "SALT_WARN", "level": "WARN",  "message": f"Salt low: {salt:.1f}% — refill soon", "time": now()})

        tds = sensors.get("tds_ppm", 0)
        if tds >= 500:
            alerts.append({"id": "HIGH_TDS",   "level": "ALERT", "message": f"TDS high: {tds:.0f} ppm — poor water quality", "time": now()})

        pres = sensors.get("water_pressure_bar", 5)
        if pres < 1.0:
            alerts.append({"id": "LOW_PRESSURE","level": "ALERT", "message": f"Low pressure: {pres} bar", "time": now()})

        if not sensors.get("power_status", True):
            alerts.append({"id": "POWER_FAIL", "level": "FAULT", "message": "Power failure detected", "time": now()})

        if state == "FAULT":
            alerts.append({"id": "FAULT",      "level": "FAULT", "message": f"Device FAULT: {data.get('fault_reason','Unknown')}", "time": now()})

        self.alerts = alerts

    def get_alerts(self):
        with self.lock:
            return list(getattr(self, 'alerts', []))

    def get_health_score(self):
        with self.lock:
            data    = self.telemetry
            sensors = data.get("sensors", {})
            state   = data.get("state", "")

        if not sensors:
            return {"score": None, "grade": "N/A", "factors": []}

        score, factors = 100, []
        salt = sensors.get("salt_level_pct", 100)
        if salt <= 15:   score -= 35; factors.append(f"Salt critical ({salt:.0f}%)")
        elif salt <= 30: score -= 20; factors.append(f"Salt low ({salt:.0f}%)")
        elif salt <= 50: score -= 8;  factors.append(f"Salt moderate ({salt:.0f}%)")

        tds = sensors.get("tds_ppm", 150)
        if tds >= 500:   score -= 25; factors.append(f"TDS high ({tds:.0f} ppm)")
        elif tds >= 350: score -= 12; factors.append(f"TDS elevated ({tds:.0f} ppm)")

        pres = sensors.get("water_pressure_bar", 3)
        if pres < 1.0:   score -= 20; factors.append(f"Pressure critical ({pres} bar)")
        elif pres < 1.5: score -= 10; factors.append(f"Pressure low ({pres} bar)")

        if state == "FAULT":
            score -= 30; factors.append("Device in FAULT state")
        if not sensors.get("power_status", True):
            score -= 20; factors.append("Power failure")

        score = max(0, min(100, score))
        grade = ("Excellent" if score >= 85 else "Good" if score >= 70 else
                 "Fair" if score >= 50 else "Poor" if score >= 30 else "Critical")
        return {"score": score, "grade": grade, "factors": factors}

storage = Storage()

# ── MQTT Setup ─────────────────────────────────────────────────────────────────

BROKER  = "localhost"
PORT    = 1883
TELEMETRY_TOPIC = "ecowell/ECOWELL_001/telemetry"
EVENT_TOPIC     = "ecowell/ECOWELL_001/events"
COMMAND_TOPIC   = "ecowell/ECOWELL_001/command"

_mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ecowell-backend")

def on_connect(client, userdata, flags, rc, props=None):
    print(f"[Backend MQTT] Connected (rc={rc})")
    client.subscribe(TELEMETRY_TOPIC)
    client.subscribe(EVENT_TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        if msg.topic == TELEMETRY_TOPIC:
            storage.update_telemetry(payload)
        elif msg.topic == EVENT_TOPIC:
            storage.add_event(payload)
    except Exception as e:
        print(f"[Backend MQTT] Parse error: {e}")

_mqtt_client.on_connect = on_connect
_mqtt_client.on_message = on_message

def start_mqtt():
    try:
        _mqtt_client.connect(BROKER, PORT, 60)
        _mqtt_client.loop_start()
        print(f"[Backend MQTT] Connecting to {BROKER}:{PORT}")
    except Exception as e:
        print(f"[Backend MQTT] Warning: Could not connect to broker: {e}")

# ── Flask App ──────────────────────────────────────────────────────────────────

app = Flask(__name__)

import traceback

@app.errorhandler(Exception)
def handle_exception(e):
    print("!!! EXCEPTION OCCURRED !!!")
    traceback.print_exc()
    return jsonify({"error": str(e)}), 500

# Enable CORS for dashboard
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@app.route("/")
def home():
    return jsonify({"message": "EcoWell IoT Backend Running", "status": "ok"})

@app.route("/health")
def health():
    return jsonify({"status": "running"})

@app.route("/telemetry")
def get_telemetry():
    return jsonify(storage.get_telemetry())

@app.route("/events")
def get_events():
    return jsonify(storage.get_events())

@app.route("/alerts")
def get_alerts():
    return jsonify(storage.get_alerts())

@app.route("/health-score")
def get_health_score():
    return jsonify(storage.get_health_score())

@app.route("/dashboard")
def dashboard():
    return jsonify({
        "telemetry": storage.get_telemetry(),
        "events":    storage.get_events(),
    })

ALLOWED_COMMANDS = {
    "regenerate", "force_low_salt", "force_low_pressure",
    "force_high_tds", "force_power_failure", "force_regen_fail", "reset_debug", "ota_update"
}

@app.route("/command", methods=["POST", "OPTIONS"])
def send_command():
    if request.method == "OPTIONS":
        return "", 200
    body = request.get_json(force=True) or {}
    cmd  = body.get("command", "").strip()

    if cmd not in ALLOWED_COMMANDS:
        return jsonify({"error": f"Unknown command: {cmd}"}), 400

    try:
        result = _mqtt_client.publish(COMMAND_TOPIC, cmd)
        storage.add_event({
            "time":    datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level":   "INFO",
            "message": f"[Dashboard] Remote command sent: {cmd}",
        })
        return jsonify({"status": "sent", "command": cmd})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

import os

@app.route("/device-logs")
def get_device_logs():
    log_path = os.path.join(os.path.dirname(__file__), "..", "device", "device_activity.log")
    try:
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                return f.read(), 200, {"Content-Type": "text/plain"}
        return "Log file not found", 404
    except Exception as e:
        return str(e), 500

# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  EcoWell IoT Backend (Flask)")
    print("  API: http://localhost:8000")
    print("  Docs: http://localhost:8000/")
    print("=" * 55)
    start_mqtt()
    # Use threading=True so MQTT + Flask work together
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)