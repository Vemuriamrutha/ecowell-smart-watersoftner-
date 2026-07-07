# EcoWell Smart Water Softener — IoT Controller MVP

> **IoT Engineer Intern Assignment | EcoWell India**  
> Python-based device simulator · FastAPI backend · MQTT · Real-time web dashboard

---

## 📌 Table of Contents
- [Problem Understanding](#-problem-understanding)
- [System Architecture](#-system-architecture)
- [Component Overview](#-component-overview)
- [MQTT Topics & API Endpoints](#-mqtt-topics--api-endpoints)
- [Device State Machine](#-device-state-machine)
- [Safety Checks Before Regeneration](#-safety-checks-before-regeneration)
- [How to Run](#-how-to-run)
- [Demo Flow](#-demo-flow)
- [Known Limitations](#-known-limitations)
- [V2 Improvements](#-v2-improvements)

---

## 🎯 Problem Understanding

A residential water softener removes hardness minerals (Ca²⁺, Mg²⁺) from water using an ion-exchange resin bed saturated with salt (NaCl). Over time:

- **Salt depletes** → resin can no longer exchange ions → water hardness increases (TDS rises)
- **Regeneration** restores the resin by flushing it with a strong brine solution

The challenge: trigger regeneration at the right time, not blindly. The wrong conditions (critically low salt, low pressure, power off) will make regeneration fail or damage the unit.

This MVP demonstrates:
- Real-time sensor monitoring (flow, pressure, salt, TDS, power)
- A safe state machine managing the device lifecycle
- Remote regeneration with multi-point safety checks
- Cloud-connected dashboard for monitoring and control

---

## 🏗 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DEVICE LAYER (Python)                     │
│                                                              │
│  ┌────────────┐   ┌──────────────┐   ┌──────────────────┐  │
│  │ SensorModel│──▶│ StateMachine │──▶│  EventLog        │  │
│  │ (sensors.py│   │(state_machine│   │  (events.py)     │  │
│  │            │   │    .py)      │   └──────────────────┘  │
│  └────────────┘   └──────┬───────┘                          │
│                          │                                   │
│              ┌───────────▼──────────┐                       │
│              │   Device (simulator) │                       │
│              │     + Safety checks  │                       │
│              │     + Persistence    │                       │
│              └───────────┬──────────┘                       │
└──────────────────────────┼──────────────────────────────────┘
                           │ MQTT (paho)
                           │
              ┌────────────▼────────────┐
              │   MOSQUITTO BROKER      │
              │   localhost:1883        │
              └────┬────────────────────┘
                   │                │
      telemetry /  │                │  command topic
      events topics│                │  (backend → device)
                   │                │
┌──────────────────▼────────────────▼──────────────────────┐
│                   BACKEND LAYER (FastAPI)                  │
│                                                            │
│  ┌─────────────┐   ┌──────────┐   ┌────────────────────┐ │
│  │ mqtt_handler│──▶│ storage  │──▶│  REST API (routes) │ │
│  │ (subscriber)│   │ (in-mem) │   │  + /command (POST) │ │
│  └─────────────┘   └──────────┘   └─────────┬──────────┘ │
└──────────────────────────────────────────────┼────────────┘
                                               │ HTTP
                                               │
                         ┌─────────────────────▼────────┐
                         │   DASHBOARD (Flask + HTML)    │
                         │   Polls /api/dashboard        │
                         │   Posts /api/command          │
                         │   localhost:5000              │
                         └──────────────────────────────┘
```

---

## 🧩 Component Overview

| File | Purpose |
|------|---------|
| `device/sensors.py` | Simulates all 5 sensors with realistic noise; supports debug flags |
| `device/state_machine.py` | 5-state FSM with power-edge detection, timeout watchdog |
| `device/safety.py` | Pre-regeneration safety gate (salt, pressure, power, state) |
| `device/events.py` | In-memory circular event log (last 100 entries) |
| `device/persistance.py` | JSON-based state persistence across restarts |
| `device/mqtt_client.py` | paho-mqtt wrapper; publishes telemetry & events, subscribes to commands |
| `device/simulator.py` | Main device loop with predictive alerts + debug console |
| `backend/main.py` | FastAPI app; /alerts, /health-score endpoints |
| `backend/mqtt_handler.py` | MQTT subscriber; feeds storage |
| `backend/storage.py` | Thread-safe store; derives active alerts + device health score |
| `backend/routes.py` | REST endpoints including POST /command |
| `dashboard/app.py` | Flask proxy; aggregates telemetry + alerts + health score |
| `dashboard/templates/index.html` | Single-page dashboard UI |
| `dashboard/static/style.css` | Dark glassmorphism design |
| `dashboard/static/dashboard.js` | Live polling, command dispatch, safety check visualizer |

---

## 📡 MQTT Topics & API Endpoints

### MQTT Topics

| Topic | Direction | Payload |
|-------|-----------|---------|
| `ecowell/ECOWELL_001/telemetry` | Device → Backend | JSON: state, sensors, regen_status, health_hint |
| `ecowell/ECOWELL_001/events` | Device → Backend | JSON: time, level, message |
| `ecowell/ECOWELL_001/command` | Backend → Device | Plain string: e.g. `regenerate` |

### REST API (FastAPI — port 8000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/telemetry` | Latest telemetry snapshot |
| GET | `/events` | Last 200 events |
| GET | `/dashboard` | Combined telemetry + events |
| GET | `/alerts` | Active derived alerts |
| GET | `/health-score` | Device health score (0–100) + grade |
| GET | `/health` | Backend liveness check |
| **POST** | `/command` | Send command to device via MQTT |

**POST /command body:**
```json
{ "command": "regenerate" }
```

**Valid commands:** `regenerate`, `force_low_salt`, `force_low_pressure`, `force_high_tds`, `force_power_failure`, `force_regen_fail`, `reset_debug`

---

## 🔄 Device State Machine

```
                    ┌──────┐
        power on    │ IDLE │
    ───────────────▶│      │
                    └──┬───┘
                       │ always
                       ▼
                 ┌────────────┐
        ◀────── │ MONITORING │ ──────────────────────────────┐
        │        └────┬───────┘                               │
        │             │ salt ≤ 15%                            │ pressure < 1 bar
        │             │ or TDS ≥ 500 ppm                      │ or power failure
        │             ▼                                       ▼
        │  ┌──────────────────────┐               ┌────────────────┐
        │  │ REGENERATION_REQUIRED│               │    FAULT       │
        │  └──────────┬───────────┘               └──────┬─────────┘
        │             │ command received                   │ power restored
        │             │ + safety OK                        │ → MONITORING
        │             ▼                                    │
        │  ┌──────────────────────┐               ────────┘
        │  │ REGENERATION_RUNNING │
        │  └──────────┬───────────┘
        │             │ success (15s)        timeout (25s) or force-fail
        └─────────────┘                     ────────────────────────────▶ FAULT
```

---

## 🛡 Safety Checks Before Regeneration

Before accepting any regeneration command (remote or local), the device validates:

| Check | Threshold | Reason |
|-------|-----------|--------|
| **Salt level** | > 15% | Need salt to create brine solution |
| **Water pressure** | ≥ 1.0 bar | Backwash requires adequate flow |
| **Power status** | ON | Cannot operate without power |
| **Device state** | Not FAULT, not already RUNNING | Prevent double-trigger |
| **Timeout watchdog** | 25 seconds | Auto-FAULT if cycle hangs |

If any check fails, the command is rejected with a logged reason — no blind actuation.

---

## 🚀 How to Run

### Prerequisites
- Python 3.11+ (Standard libraries only, zero external systems like Mosquitto required!)

### Easy Launch (Windows Batch Script)
Double-click the `start_all.bat` file in the root folder. It will automatically launch:
1. Pure Python MQTT Broker on Port 1883
2. Flask Backend API on Port 8000
3. Flask Web Dashboard on Port 5000
4. Device Logic Simulator Console

Alternatively, open your browser to `http://localhost:5000`.

---

### Manual Launch (Cross-Platform)

If you prefer to start components manually, run the following in separate terminals:

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the MQTT Broker:**
   ```bash
   python broker.py
   ```

3. **Start the Backend API:**
   ```bash
   cd backend
   python main.py
   ```

4. **Start the Device Simulator:**
   ```bash
   cd device
   python simulator.py
   ```

5. **Start the Dashboard Server:**
   ```bash
   cd dashboard
   python app.py
   ```

6. **Verify API Endpoints (Optional Test Script):**
   ```bash
   python test_api.py
   ```


---

## 🎬 Demo Flow

1. Open dashboard at `http://localhost:5000`
2. Watch sensor values update live (every 1.5 seconds)
3. Observe device state transition: `IDLE → MONITORING`
4. Click **Simulate Low Salt** → salt drops to 10% → state becomes `REGENERATION_REQUIRED`
5. Attempt to click **Start Regeneration** → watch safety checks panel turn red/green
6. Click **Reset Debug Conditions** → salt recovers → safety checks pass
7. Click **Start Regeneration** → state → `REGENERATION_RUNNING` → completes → `MONITORING`
8. Click **Simulate Power Failure** → state → `FAULT` → events log updates
9. Click **Reset** → power restores → `MONITORING` resumes

---

## 🛡️ Enterprise-Grade Resilience Features

We have implemented robust, real-world mechanisms to handle hardware/network instability:

1. **MQTT Store-and-Forward Offline Queueing:**
   If the device loses connection to the MQTT broker (e.g. if the network drops or broker is shut down), it doesn't lose telemetry. Telemetry is buffered in an in-memory queue. The moment the connection is re-established, the queue automatically flushes all stored messages to the broker in chronological order.
   * *How to demo:* Close the MQTT Broker terminal window, let the simulator tick a few times (you'll see `[MQTT] [Resilience] Client offline. Message queued`), then start `python broker.py` again. Watch the messages automatically flush!

2. **Persistent Local Activity Logging:**
   The simulator automatically logs all state machine transitions, safety alerts, and command results to a persistent local log file at `device/device_activity.log` simulating an on-board Flash memory logging system.

---

## ⚠ Known Limitations

| Limitation | Explanation |
|------------|-------------|
| In-memory only | Backend storage resets on restart; no persistent database (SQLite/Postgres) |
| Single device | System currently supports one device ID (`ECOWELL_001`) |
| No auth | Dashboard has no login/token protection — acceptable for local demo |
| Simulated sensors | All values are software-generated; no real hardware attached |
| No MQTT TLS | Broker runs without SSL; production would need certificates |
| Salt depletion speed | Depletion rate accelerated for demo purposes (would be much slower in real hardware) |

---

## 🔮 V2 Improvements

| Feature | Implementation Idea |
|---------|-------------------|
| **Hardware integration** | Replace SensorModel with actual ESP32 + flow/TDS/pressure sensors |
| **Database persistence** | SQLite or TimescaleDB for full event history and analytics |
| **Multi-device support** | Device registry, dynamic MQTT topic routing |
| **MQTT TLS + auth** | Mosquitto ACLs + TLS certificates for field deployment |
| **WhatsApp/Email alerts** | Twilio or SendGrid webhook on FAULT events |
| **OTA firmware updates** | MQTT-based firmware version check + binary delivery |
| **Mobile app** | React Native app consuming the same REST API |
| **ML predictive maintenance** | Salt depletion prediction from historical data |
| **Enclosure design** | IP65 rated PCB mount with OLED local display |


---

## 📐 Architecture Notes

**Why MQTT?**  
MQTT's pub/sub model is ideal for IoT: low bandwidth, supports QoS levels, naturally decouples device from cloud. The device can keep publishing even if the backend restarts.

**Why separate backend + dashboard?**  
The FastAPI backend acts as the "source of truth" for device data. The Flask dashboard is a thin proxy — in production, this would be a mobile app or cloud frontend hitting the same API.

**Why Python simulator instead of ESP32?**  
The Python simulator faithfully reproduces the exact same logic that would run on embedded hardware. The MQTT protocol, safety checks, and state machine are 1:1 portable to MicroPython on ESP32.
