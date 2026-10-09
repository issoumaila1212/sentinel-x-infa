# run_sentinel_live.py
import json
import ssl
import time
import cv2
import paho.mqtt.client as mqtt
from model_class import SentinelAI

# ==================== CREDENTIALS & NETWORK CONFIG ====================
MQTT_HOST = "10.62.75.50"               # Broker Host / IP (Raspberry Pi)
MQTT_PORT = 8883                        # 8883 for TLS
MQTT_USER = "ia"                        # Your MQTT username
MQTT_PASS = "J7w5XRXtbCkkNeQsUahADIArluY"       # Your MQTT password

# Path to the CA certificate file (.crt or .pem) on your PC
CA_CERT_PATH = "mosquitto/certs/ca.crt"

# Topics
MQTT_TOPIC_TELEMETRY = "sentinel/telemetry"       # Inbound JSON from hardware
MQTT_TOPIC_DASHBOARD = "sentinel/admin/dashboard" # Outbound diagnostic JSON for web UI

# Camera Stream URL (go2rtc / MJPEG on the Pi, port 1984)
STREAM_URL = "http://10.62.75.50:1984/api/stream.mjpeg?src=cam01"
# ======================================================================

print("=" * 80)
print("SENTINEL-X : LIVE SYSTEM DEPLOYMENT")
print(f"Target Gateway: {MQTT_HOST}:{MQTT_PORT} (TLS Encrypted)")
print(f"Video Stream  : {STREAM_URL}")
print("=" * 80)

# Initialize SentinelAI (15 calibration cycles, 5.0s idle scan, 10.0s alarm hold)
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
    msg = connection_codes.get(rc, f"Error code {rc}")
    
    if rc == 0:
        print(f"\n[MQTT/TLS] {msg} to broker {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC_TELEMETRY)
        print(f"[MQTT] Subscribed to telemetry topic: '{MQTT_TOPIC_TELEMETRY}'")
        print("[SYSTEM] Collecting first 15 readings for baseline calibration...\n")
    else:
        print(f"\n[MQTT ERROR] {msg} (code {rc})")

def on_message(client, userdata, msg):
    try:
        raw_payload = msg.payload.decode("utf-8")
        data = json.loads(raw_payload)

        # 1. Extract physical readings (HC-SR04 & DHT22, no PIR dependency)
        dist = float(data.get("distance", data.get("dist", 220.0)))
        temp = float(data.get("temperature", data.get("temp", 21.0)))
        hum  = float(data.get("humidity", data.get("hum", 50.0)))

        # 2. Feed into SentinelAI pipeline
        result = ai.process_reading(dist=dist, temp=temp, hum=hum)

        threat = result.get("threat_level", "UNKNOWN")
        alerts = result.get("active_alerts", [])
        status = result.get("status", "ACTIVE")
        cooldown = result.get("cooldown_remaining_sec", 0.0)
        anomaly = result.get("anomaly", False)

        # 3. Terminal logging
        print(
            f"[{time.strftime('%H:%M:%S')}] {status:<16} | "
            f"Threat: {threat:<24} | "
            f"D: {dist:5.1f}cm | T: {temp:4.1f}°C | "
            f"Cool: {cooldown:4.1f}s | "
            f"Alerts: {alerts}"
        )

        # 4. Display live video feed with HUD overlays
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

            # Cooldown HUD Banner
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

        # 5. Republish aggregated verdict to dashboard topic
        dashboard_packet = {k: v for k, v in result.items() if k != "frame"}
        dashboard_packet["timestamp"] = time.time()
        client.publish(MQTT_TOPIC_DASHBOARD, json.dumps(dashboard_packet))

    except json.JSONDecodeError:
        print(f"[MQTT ERROR] Malformed JSON received: {msg.payload}")
    except Exception as e:
        print(f"[PIPELINE ERROR] Unexpected error: {e}")

# ==================== MQTT CLIENT SETUP WITH TLS ====================
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
    # Allows connection when connecting via IP address rather than hostname
    client.tls_insecure_set(True)
except Exception as e:
    print(f"[TLS CONFIG ERROR] Failed to configure TLS with '{CA_CERT_PATH}': {e}")
    print("Verify the path to your CA certificate file.")

client.on_connect = on_connect
client.on_message = on_message

# ==================== MAIN EXECUTION ====================
try:
    print(f"[SYSTEM] Connecting to secure broker {MQTT_HOST}:{MQTT_PORT}...")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    
    # Process network loop
    client.loop_forever()

except KeyboardInterrupt:
    print("\n[SYSTEM] Safe shutdown requested by user.")
finally:
    client.disconnect()
    ai.close()
    cv2.destroyAllWindows()
    print("[SYSTEM] Closed cleanly.")