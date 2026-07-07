import json
import paho.mqtt.client as mqtt
from storage import storage

BROKER = "localhost"
PORT = 1883

TELEMETRY_TOPIC = "ecowell/ECOWELL_001/telemetry"
EVENT_TOPIC     = "ecowell/ECOWELL_001/events"


def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[MQTT] Backend connected to broker (rc={rc})")
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
        print(f"[MQTT] Parse error: {e}")


_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ecowell-backend")
_client.on_connect = on_connect
_client.on_message = on_message


def start_mqtt():
    _client.connect(BROKER, PORT, 60)
    _client.loop_start()