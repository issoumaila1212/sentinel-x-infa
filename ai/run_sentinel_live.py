# run_sentinel_live.py
import json
import ssl
import time
import cv2
import paho.mqtt.client as mqtt
from model_class import SentinelAI

# ==================== CREDENTIALS & NETWORK CONFIG ====================
MQTT_HOST = "10.62.75.50"               # Broker Host / IP
MQTT_PORT = 8883                        # 8883 is standard for MQTT over TLS (use 1883 if non-TLS)
MQTT_USER = "ia"            # Your MQTT username
MQTT_PASS = "J7w5XRXtbCkkNeQsUahADIArluY"       # Your MQTT password

# Path to the CA certificate file (.crt or .pem) on your PC
CA_CERT_PATH = "mosquitto/certs/ca.crt"                 # e.g., "certs/ca.crt" or r"C:\certs\ca.crt"

# Topics
MQTT_TOPIC_TELEMETRY = "sentinel/telemetry"       # Topic where the Pi publishes JSON
MQTT_TOPIC_DASHBOARD = "sentinel/admin/dashboard" # Topic where this script republishes AI verdicts

# Camera Stream URL (go2rtc / MJPEG on the Pi)
STREAM_URL = "http://10.62.75.50:8883/api/stream.mjpeg?src=cam01"
# ======================================================================

# Initialize SentinelAI (15 baseline calibration cycles, 2.0s heartbeat fallback)
ai = SentinelAI(calibration_samples=15, stream_source=STREAM_URL, heartbeat_interval=2.0)

def on_connect(client, userdata, flags, rc):
    connection_codes = {
        0: "Connected successfully",
        1: "Connection refused - incorrect protocol version",
        2: "Connection refused - invalid client identifier",
        3: "Connection refused - server unavailable",
        4: "Connection refused - bad username or password",
        5: "Connection refused - not authorized / TLS handshake error"
    }
    msg = connection_codes.get(rc, f"Unknown error code {rc}")
    
    if rc == 0:
        print(f"[MQTT/TLS] {msg} to {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC_TELEMETRY)
        print(f"[MQTT] Subscribed to telemetry topic: '{MQTT_TOPIC_TELEMETRY}'")
    else:
        print(f"[MQTT ERROR] {msg} (code {rc})")

def on_message(client, userdata, msg):
    try:
        raw_payload = msg.payload.decode("utf-8")
        data = json.loads(raw_payload)

        # Robust extraction supporting potential key variations
        pir = int(data.get("pir", data.get("presence", 0)))
        dist = float(data.get("distance", data.get("dist", 220.0)))
        temp = float(data.get("temperature", data.get("temp", 21.0)))
        hum = float(data.get("humidity", data.get("hum", 50.0)))

        # Process through Sentinel-X multi-threat engine
        result = ai.process_reading(pir=pir, dist=dist, temp=temp, hum=hum)

        threat = result.get("threat_level", result.get("threat", "UNKNOWN"))
        alerts = result.get("active_alerts", [])
        status = result.get("status", "ACTIVE")

        # Terminal Log
        print(
            f"[{time.strftime('%H:%M:%S')}] {status:<18} | "
            f"Threat: {threat:<24} | "
            f"Alerts: {str(alerts):<40} | "
            f"D: {dist:5.1f}cm | T: {temp:4.1f}°C | PIR: {pir}"
        )

        # Overlay on Camera Frame & Render Window
        frame = result.get("frame")
        if frame is not None:
            display_frame = frame.copy()
            is_danger = any(k in threat for k in ["CRITICAL", "HAZARD"])
            badge_color = (0, 0, 255) if is_danger else (0, 255, 0)

            # Banner 1: Overall Threat
            cv2.putText(
                display_frame,
                f"THREAT: {threat}",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                badge_color,
                2
            )

            # Banner 2: Active Alerts List
            if alerts:
                cv2.putText(
                    display_frame,
                    f"ALERTS: {', '.join(alerts)}",
                    (20, 65),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 165, 255),
                    2
                )

            cv2.imshow("Sentinel-X Central Monitor (Live Hardware)", display_frame)
            cv2.waitKey(1)

        # Forward complete diagnostic output (without binary frame) to dashboard
        dashboard_packet = {k: v for k, v in result.items() if k != "frame"}
        client.publish(MQTT_TOPIC_DASHBOARD, json.dumps(dashboard_packet))

    except json.JSONDecodeError:
        print(f"[MQTT ERROR] Received malformed JSON string: {msg.payload}")
    except Exception as e:
        print(f"[PIPELINE ERROR] Unexpected error: {e}")

# ----------------- MQTT CLIENT SETUP WITH TLS -----------------
client = mqtt.Client()

# 1. Set Username & Password
client.username_pw_set(username=MQTT_USER, password=MQTT_PASS)

# 2. Configure TLS / SSL Context
#    tls_set enables SSL encryption using the broker's CA certificate
try:
    client.tls_set(
        ca_certs=CA_CERT_PATH,
        certfile=None,
        keyfile=None,
        cert_reqs=ssl.CERT_REQUIRED,
        tls_version=ssl.PROTOCOL_TLS_CLIENT
    )
    # If the certificate domain name doesn't match the raw IP address, bypass hostname check:
    client.tls_insecure_set(True)
except Exception as e:
    print(f"[TLS SETUP ERROR] Could not configure TLS: {e}")
    print("Verify the path to your CA certificate file.")

client.on_connect = on_connect
client.on_message = on_message

# ----------------- MAIN EXECUTION LOOP -----------------
try:
    print(f"[SYSTEM] Connecting to secure broker {MQTT_HOST}:{MQTT_PORT}...")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    
    # loop_forever manages network traffic, handles ping packets, and reconnects automatically
    client.loop_forever()

except KeyboardInterrupt:
    print("\n[SYSTEM] Safe shutdown requested by user.")
finally:
    client.disconnect()
    ai.close()
    cv2.destroyAllWindows()