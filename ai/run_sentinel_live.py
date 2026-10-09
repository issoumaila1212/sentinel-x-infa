# run_sentinel_live.py
import json
import ssl
import time
import cv2
import paho.mqtt.client as mqtt
from model_class import SentinelAI

# ==================== NETWORK & CREDENTIALS CONFIG ====================
MQTT_HOST = "10.62.75.50"               
MQTT_PORT = 8883                        # 1883 non-TLS)
MQTT_USER = "sentinel_admin"            
MQTT_PASS = "J7w5XRXtbCkkNeQsUahADIArluY"      

CA_CERT_PATH = "mosquitto/certs/ca.crt"             

# MQTT Topics
MQTT_TOPIC_TELEMETRY = "sentinel/telemetry"       # Published by serial_mqtt_bridge.py
MQTT_TOPIC_DASHBOARD = "sentinel/admin/dashboard" # Republished diagnostic output

STREAM_URL = "http://10.62.75.50:1984/api/stream.mjpeg?src=cam01"
# ======================================================================

print("=" * 75)
print("SENTINEL-X : LIVE HARDWARE DEPLOYMENT")
print(f"Target Gateway: {MQTT_HOST}:{MQTT_PORT} (TLS Encrypted)")
print(f"Video Stream  : {STREAM_URL}")
print("=" * 75)

# Initialize SentinelAI:
# - calibration_samples: 15 frames of calm baseline
# - idle_heartbeat: 5.0 seconds
# - alarm_hold_duration: 10.0 seconds cooldown
ai = SentinelAI(
    calibration_samples=15,
    stream_source=STREAM_URL,
    idle_heartbeat=5.0,
    alarm_hold_duration=10.0
)

def on_connect(client, userdata, flags, rc):
    connection_codes = {
        0: "Connected successfully",
        1: "Refused - incorrect protocol version",
        2: "Refused - invalid client identifier",
        3: "Refused - server unavailable",
        4: "Refused - bad username or password",
        5: "Refused - not authorized / TLS handshake error"
    }
    status_text = connection_codes.get(rc, f"Error code {rc}")
    
    if rc == 0:
        print(f"\n[MQTT/TLS] {status_text} to broker {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC_TELEMETRY)
        print(f"[MQTT] Subscribed to topic: '{MQTT_TOPIC_TELEMETRY}'")
        print("[SYSTEM] Ready. Gathering first 15 readings for baseline calibration...\n")
    else:
        print(f"\n[MQTT ERROR] {status_text} (code {rc})")

def on_message(client, userdata, msg):
    try:
        raw_payload = msg.payload.decode("utf-8")
        data = json.loads(raw_payload)

        #Extract physical readings (HC-SR04 & DHT22)
        dist = float(data.get("distance", data.get("dist", 220.0)))
        temp = float(data.get("temperature", data.get("temp", 21.0)))
        hum  = float(data.get("humidity", data.get("hum", 50.0)))

        #Feed into SentinelAI pipeline
        result = ai.process_reading(dist=dist, temp=temp, hum=hum)

        threat = result.get("threat_level", "UNKNOWN")
        alerts = result.get("active_alerts", [])
        status = result.get("status", "ACTIVE")
        cooldown = result.get("cooldown_remaining_sec", 0.0)
        anomaly = result.get("anomaly", False)

        #Terminal logging
        print(
            f"[{time.strftime('%H:%M:%S')}] {status:<16} | "
            f"Threat: {threat:<24} | "
            f"D: {dist:5.1f}cm | T: {temp:4.1f}°C | "
            f"Cool: {cooldown:4.1f}s | "
            f"Alerts: {alerts}"
        )

        #Display live video feed with HUD overlays
        frame = result.get("frame")
        if frame is not None:
            display_frame = frame.copy()
            
            is_danger = any(k in threat for k in ["CRITICAL", "HAZARD"])
            badge_color = (0, 0, 255) if is_danger else (0, 255, 0)

            # Top HUD: Threat Status
            cv2.putText(
                display_frame,
                f"STATUS: {status} | THREAT: {threat}",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                badge_color,
                2
            )

            # Cooldown HUD
            if cooldown > 0:
                cv2.putText(
                    display_frame,
                    f"HOLD COOLDOWN: {cooldown:.1f}s",
                    (20, 65),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 215, 255),
                    2
                )

            # Bottom HUD: Sensor Telemetry
            telemetry_line = f"Dist: {dist:.1f}cm  Temp: {temp:.1f}C  Hum: {hum:.1f}%"
            cv2.putText(
                display_frame,
                telemetry_line,
                (20, 430),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (200, 200, 200),
                1
            )

            # Active Alerts
            if alerts:
                cv2.putText(
                    display_frame,
                    f"ALERTS: {', '.join(alerts)}",
                    (20, 460),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 165, 255),
                    2
                )

            cv2.imshow("Sentinel-X Central Station (Live Hardware)", display_frame)
            cv2.waitKey(1)

        #Republish aggregated verdict to dashboard topic
        dashboard_packet = {k: v for k, v in result.items() if k != "frame"}
        dashboard_packet["timestamp"] = time.time()
        client.publish(MQTT_TOPIC_DASHBOARD, json.dumps(dashboard_packet))

    except json.JSONDecodeError:
        print(f"[MQTT ERROR] Malformed JSON received: {msg.payload}")
    except Exception as e:
        print(f"[PIPELINE ERROR] Unexpected error: {e}")

# ==================== MQTT & TLS SETUP ====================
client = mqtt.Client()
client.username_pw_set(username=MQTT_USER, password=MQTT_PASS)

try:
    client.tls_set(
        ca_certs=CA_CERT_PATH,
        certfile=None,
        keyfile=None,
        cert_reqs=ssl.CERT_REQUIRED,
        tls_version=ssl.PROTOCOL_TLS_CLIENT
    )
    #Allows connection when connecting via IP address rather than a domain name
    client.tls_insecure_set(True)
except Exception as e:
    print(f"[TLS CONFIG ERROR] Failed to set up TLS with '{CA_CERT_PATH}': {e}")
    print("Make sure the CA certificate file is placed in this directory.")

client.on_connect = on_connect
client.on_message = on_message

# ==================== MAIN EXECUTION ====================
try:
    print(f"[SYSTEM] Connecting to {MQTT_HOST}:{MQTT_PORT}...")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    
    # Process network loop
    client.loop_forever()

except KeyboardInterrupt:
    print("\n[SYSTEM] Termination requested by user.")
finally:
    client.disconnect()
    ai.close()
    cv2.destroyAllWindows()
    print("[SYSTEM] Closed cleanly.")