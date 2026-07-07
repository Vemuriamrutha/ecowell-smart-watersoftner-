import json
import paho.mqtt.client as mqtt
import config


def create_client(client_id, on_command_received):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.offline_queue = []

    def on_connect(c, userdata, flags, rc, properties=None):
        print(f"[MQTT] Connected with result code {rc}")
        c.subscribe(config.MQTT_COMMAND_TOPIC)
        # Flush offline queued messages upon reconnection
        if hasattr(c, "offline_queue") and c.offline_queue:
            print(f"[MQTT] Reconnected! Flushing {len(c.offline_queue)} queued messages...")
            for t, p in c.offline_queue:
                c.publish(t, p)
            c.offline_queue.clear()

    def on_message(c, userdata, msg):
        command = msg.payload.decode().strip()
        print(f"[MQTT] Command received on {msg.topic}: {command}")
        on_command_received(command)

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(config.MQTT_BROKER, config.MQTT_PORT, keepalive=60)
    except Exception as e:
        print(f"[MQTT] Initial connection failed: {e}. Will attempt auto-reconnect.")

    client.loop_start()
    return client


def publish_json(client, topic, payload_dict):
    payload = json.dumps(payload_dict)
    if client.is_connected():
        client.publish(topic, payload)
    else:
        if not hasattr(client, "offline_queue"):
            client.offline_queue = []
        client.offline_queue.append((topic, payload))
        if len(client.offline_queue) > 50:
            client.offline_queue.pop(0)
        print(f"[MQTT] [Resilience] Client offline. Message queued (size: {len(client.offline_queue)})")