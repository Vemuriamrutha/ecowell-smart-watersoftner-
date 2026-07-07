from flask import Flask, render_template, jsonify, request
import requests

app = Flask(__name__)

BACKEND_URL = "http://127.0.0.1:8000"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/dashboard")
def dashboard():
    try:
        r = requests.get(f"{BACKEND_URL}/dashboard", timeout=2)
        data = r.json()
    except Exception as e:
        data = {"telemetry": {}, "events": [], "error": str(e)}

    # Enrich with alerts and health score
    try:
        data["alerts"] = requests.get(f"{BACKEND_URL}/alerts", timeout=2).json()
    except Exception:
        data["alerts"] = []

    try:
        data["health"] = requests.get(f"{BACKEND_URL}/health-score", timeout=2).json()
    except Exception:
        data["health"] = {}

    return jsonify(data)


@app.route("/api/command", methods=["POST"])
def send_command():
    body = request.get_json(force=True)
    try:
        r = requests.post(
            f"{BACKEND_URL}/command",
            json=body,
            timeout=3,
        )
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/logs/download")
def download_logs():
    try:
        r = requests.get(f"{BACKEND_URL}/device-logs", timeout=3)
        return r.text, r.status_code, {
            "Content-Type": "text/plain",
            "Content-Disposition": "attachment; filename=device_activity.log"
        }
    except Exception as e:
        return str(e), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)