import json
import os

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from database import insert_alert, insert_reading

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

# Deux familles de topics :
#   aether/<device>/sensors -> lectures brutes des capteurs (noeuds ESP8266 / Arduino+Pi)
#   aether/<device>/alerts  -> alertes deja qualifiees, envoyees par d'autres systemes
#                              (ex: la detection video de l'equipe IA). Compte MQTT dedie "ia".
SENSOR_TOPIC = "aether/+/sensors"
ALERT_TOPIC = "aether/+/alerts"

MEASURES = ("temperature", "humidity", "gas", "presence", "distance")
RANGES = {
    "temperature": (-40, 80),
    "humidity": (0, 100),
    "gas": (0, 1024),
    "distance": (0, 450),
}
ALERT_LEVELS = ("info", "warning", "critical")

# --- Seuils de securite (capteurs) ------------------------------------------
# Pour chaque mesure : liste de regles (operateur, seuil, niveau, message),
# triees de la plus grave a la moins grave. La premiere regle qui correspond
# gagne. Facile a retoucher pour la demo.
THRESHOLDS = {
    "temperature": [
        (">", 38, "critical", "Temperature anormalement elevee"),
        (">", 30, "warning", "Temperature elevee"),
        ("<", 5, "warning", "Temperature basse"),
    ],
    "humidity": [
        (">", 85, "warning", "Humidite elevee"),
        ("<", 15, "warning", "Humidite basse"),
    ],
    "gas": [
        (">", 700, "critical", "Niveau de gaz critique"),
        (">", 400, "warning", "Niveau de gaz eleve"),
    ],
    "distance": [
        ("<", 15, "warning", "Objet detecte a proximite immediate"),
    ],
    "presence": [
        ("==", 1, "info", "Mouvement detecte"),
    ],
}

# Etat en memoire (device, mesure) -> dernier niveau declenche.
# Les alertes capteurs sont "edge-triggered" : on ne les relance qu'au
# CHANGEMENT de niveau, pour ne pas spammer la table a chaque message MQTT
# (~toutes les 10s). Les alertes IA (deja discretes par nature) ne passent
# pas par ce mecanisme : chaque message IA recu produit une alerte.
_last_level = {}


def check_thresholds(data):
    device = data["device"]
    raised = []

    for measure, rules in THRESHOLDS.items():
        value = data.get(measure)
        if value is None:
            continue
        value = float(value)

        level = message = None
        for op, limit, lvl, msg in rules:
            hit = (
                (op == ">" and value > limit)
                or (op == "<" and value < limit)
                or (op == "==" and value == limit)
            )
            if hit:
                level, message = lvl, msg
                break  # la premiere regle correspondante (la plus grave) gagne

        key = (device, measure)
        if level is not None and level != _last_level.get(key):
            raised.append({
                "device": device,
                "source": measure,
                "level": level,
                "message": f"{message} ({value:g})",
            })
        _last_level[key] = level

    return raised


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


def validate_ai_alert(topic, data):
    if not isinstance(data, dict):
        raise ValueError("le message doit être un objet JSON")
    if "device" not in data:
        raise ValueError("champ manquant : device")
    if data["device"] != topic.split("/")[1]:
        raise ValueError("le device ne correspond pas au topic")
    if data.get("level") not in ALERT_LEVELS:
        raise ValueError(f"level doit être l'un de {ALERT_LEVELS}")
    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("champ manquant ou vide : message")
    score = data.get("score")
    if score is not None:
        try:
            float(score)
        except (TypeError, ValueError):
            raise ValueError("score doit être un nombre")
    return data


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print(f"[mqtt] connexion refusée : {reason_code}")
        return
    print(f"[mqtt] connecté ({reason_code}), abonnement à {SENSOR_TOPIC} et {ALERT_TOPIC}")
    client.subscribe(SENSOR_TOPIC, qos=1)
    client.subscribe(ALERT_TOPIC, qos=1)


def on_sensor_message(msg):
    data = validate(msg.topic, json.loads(msg.payload))
    insert_reading(data)
    print(f"[ok] {msg.topic} {data}")

    for alert in check_thresholds(data):
        insert_alert(**alert)
        print(f"[alerte] {alert}")


def on_alert_message(msg):
    data = validate_ai_alert(msg.topic, json.loads(msg.payload))
    insert_alert(
        device=data["device"],
        source=data.get("source", "ia"),
        level=data["level"],
        message=data["message"],
        score=data.get("score"),
    )
    print(f"[alerte ia] {msg.topic} {data}")


def on_message(client, userdata, msg):
    try:
        if msg.topic.endswith("/sensors"):
            on_sensor_message(msg)
        elif msg.topic.endswith("/alerts"):
            on_alert_message(msg)
        else:
            print(f"[ignoré] topic inattendu : {msg.topic}")
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
