import json
import paho.mqtt.client as mqtt
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from storage import storage

router = APIRouter()

# ─── MQTT publisher for sending commands to device ───────────────────────────

BROKER = "localhost"
PORT = 1883
COMMAND_TOPIC = "ecowell/ECOWELL_001/command"

_pub_client = mqtt.Client()
_pub_client.connect_async(BROKER, PORT, 60)
_pub_client.loop_start()


class CommandRequest(BaseModel):
    command: str


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/")
def home():
    return {"message": "EcoWell Backend Running"}


@router.get("/telemetry")
def get_telemetry():
    return storage.get_telemetry()


@router.get("/events")
def get_events():
    return storage.get_events()


@router.get("/dashboard")
def dashboard():
    return {
        "telemetry": storage.get_telemetry(),
        "events":    storage.get_events(),
    }


@router.post("/command")
def send_command(req: CommandRequest):
    """
    Publish a command string to the device via MQTT.
    Valid commands: regenerate | force_low_salt | force_low_pressure |
                    force_high_tds | force_power_failure | force_regen_fail |
                    reset_debug
    """
    allowed = {
        "regenerate", "force_low_salt", "force_low_pressure",
        "force_high_tds", "force_power_failure", "force_regen_fail",
        "reset_debug",
    }
    if req.command not in allowed:
        raise HTTPException(status_code=400, detail=f"Unknown command: {req.command}")

    result = _pub_client.publish(COMMAND_TOPIC, req.command)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        raise HTTPException(status_code=500, detail="Failed to publish command to broker")

    # Log the command into the backend event store as well
    storage.add_event({
        "time":    datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "level":   "INFO",
        "message": f"[Dashboard] Command sent: {req.command}",
    })
    return {"status": "sent", "command": req.command}