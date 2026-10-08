import json
import os

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from database import insert_reading

load_dotenv()  # reads the .env file at the project root

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BROKER = os.getenv("MQTT_HOST", "localhost")
PORT = int(os.getenv("MQTT_PORT", "8883"))
USER = os.getenv("MQTT_SERVER_USER", "server")
PASSWORD = os.getenv("MQTT_SERVER_PASSWORD")
CA_CERT = os.getenv(
    "MQTT_CA_CERT",
    os.path.join(BASE_DIR, "..", "mosquitto", "certs", "ca.crt"),
)
TOPIC = "aether/+/sensors"

MEASURES = ("temperature", "humidity", "gas", "presence", "distance")
RANGES = {
    "temperature": (-40, 80),
    "humidity": (0, 100),
    "gas": (0, 1024),
    "distance": (0, 450),
}


def validate(topic, data):
    if not isinstance(data, dict):
        raise ValueError("le message doit être un objet JSON")
    if "device" not in data:
        raise ValueError("champ manquant : device")
    if data["device"] != topic.split("/")[1]:
        raise ValueError("le device ne correspond pas au topic")

    # A node can send only the sensors it has, but at least one measure is required.
    if all(data.get(m) is None for m in MEASURES):
        raise ValueError("aucune mesure dans le message")

    for field, (low, high) in RANGES.items():
        value = data.get(field)
        if value is not None and not low <= float(value) <= high:
            raise ValueError(f"{field} hors plage")

    if data.get("presence") not in (None, 0, 1, True, False):
        raise ValueError("presence doit valoir 0 ou 1")

    return data


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print(f"[mqtt] connexion refusée : {reason_code}")
        return
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
    if not PASSWORD:
        raise SystemExit("MQTT_SERVER_PASSWORD manquant : vérifie le fichier .env")
    if not os.path.exists(CA_CERT):
        raise SystemExit(f"Certificat CA introuvable : {CA_CERT} (lance gen_certs.sh)")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="aether-server")
    client.username_pw_set(USER, PASSWORD)
    client.tls_set(ca_certs=CA_CERT)  # verifies the broker certificate and its name
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.on_connect = on_connect
    client.on_message = on_message

    # connect_async + retry: the server can start before the broker is ready
    client.connect_async(BROKER, PORT, keepalive=30)
    client.loop_forever(retry_first_connection=True)
