import json
import os

import paho.mqtt.client as mqtt

from database import insert_reading

BROKER = os.getenv("MQTT_HOST", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC = "aether/+/sensors"


def validate(topic, data):
    required = {"device", "temperature", "humidity", "gas", "presence"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"champs manquants : {missing}")
    if data["device"] != topic.split("/")[1]:
        raise ValueError("le device ne correspond pas au topic")
    if not -40 <= float(data["temperature"]) <= 80:
        raise ValueError("température hors plage")
    if not 0 <= float(data["humidity"]) <= 100:
        raise ValueError("humidité hors plage")
    if not 0 <= int(data["gas"]) <= 1024:
        raise ValueError("gaz hors plage")
    return data


def on_connect(client, userdata, flags, reason_code, properties):
    print(f"[mqtt] connecté ({reason_code}), abonnement à {TOPIC}")
    client.subscribe(TOPIC, qos=1)


def on_message(client, userdata, msg):
    try:
        data = validate(msg.topic, json.loads(msg.payload))
        insert_reading(data)
        print(f"[ok] {msg.topic} {data}")
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        print(f"[rejeté] {msg.topic} : {e}")


def start():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="aether-server")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, keepalive=30)
    client.loop_forever()