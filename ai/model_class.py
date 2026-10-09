# model_class.py
import time
import cv2
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from ultralytics import YOLO


class SentinelAI:
    def __init__(self, calibration_samples=15, stream_source=None, heartbeat_interval=2.0):
        self.calibration_needed = calibration_samples
        self.baseline = []
        self.calibrated = False

        self.means = None
        self.stds = None

        # 1. Unsupervised Anomaly Detector (Learns empty room baseline)
        self.iso = IsolationForest(contamination=0.05, random_state=42)

        # 2. Supervised Threat Classifier
        self.rf = RandomForestClassifier(n_estimators=30, random_state=42)
        self._init_rf()

        # 3. Vision Layer
        self.stream_source = stream_source
        self.cap = None
        self.yolo = None
        self.camera_ready = False

        # 4. Heartbeat Timing & State Persistence
        self.heartbeat_interval = heartbeat_interval
        self.last_vision_time = 0.0
        self.last_person_detected = 0
        self.last_annotated_frame = None
        self.last_spoof_alert = False

        if stream_source is not None:
            self._setup_camera(stream_source)

    def _setup_camera(self, source):
        print(f"[VISION] Connecting to camera source: {source}")
        self.cap = cv2.VideoCapture(source)
        if self.cap.isOpened():
            self.yolo = YOLO("yolov8n.pt")
            self.camera_ready = True
            print("[VISION] YOLOv8 loaded and camera stream ready.")
        else:
            print("[VISION WARNING] Could not open camera. Running in telemetry-only mode.")

    def _init_rf(self):
        # [pir, dist, temp, hum, is_anomaly, person_detected]
        X = [
            [0, 220.0, 21.5, 50.0, 0, 0],  # 0: NOMINAL
            [1, 218.0, 21.8, 49.0, 0, 0],  # 1: SUSPICIOUS_MOTION
            [1,  45.0, 22.5, 51.0, 1, 0],  # 2: UNIDENTIFIED_OBSTACLE
            [0, 220.0, 21.5, 50.0, 0, 1],  # 3: SUSPICIOUS_PRESENCE
            [1, 215.0, 21.8, 49.0, 0, 1],  # 4: CONFIRMED_INTRUSION
            [1,  45.0, 22.5, 51.0, 1, 1],  # 5: CRITICAL_INTRUSION
            [0, 220.0, 50.0, 15.0, 1, 0],  # 6: HAZARD
            [1, 215.0, 48.0, 18.0, 1, 0],  # 6: HAZARD
        ]
        y = [
            "NOMINAL",
            "SUSPICIOUS_MOTION",
            "UNIDENTIFIED_OBSTACLE",
            "SUSPICIOUS_PRESENCE",
            "CONFIRMED_INTRUSION",
            "CRITICAL_INTRUSION",
            "HAZARD",
            "HAZARD"
        ]
        self.rf.fit(X, y)

    def _verify_with_vision(self, dist_cm):
        """Grabs latest frame and performs YOLO detection + geometric anti-spoofing."""
        if not self.camera_ready or self.cap is None:
            return 0, None, False

        ret, frame = self.cap.read()
        if not ret:
            return self.last_person_detected, self.last_annotated_frame, self.last_spoof_alert

        frame_resized = cv2.resize(frame, (640, 480))
        results = self.yolo(frame_resized, classes=[0], conf=0.5, verbose=False)
        boxes = results[0].boxes
        person_count = len(boxes)
        annotated_frame = results[0].plot()

        spoof_flag = False
        if person_count > 0:
            for b in boxes:
                _, y1, _, y2 = map(int, b.xyxy[0])
                box_h = y2 - y1
                # If bounding box is massive (>280px) but distance sensor says far away (>180cm)
                if box_h > 280 and dist_cm > 180:
                    spoof_flag = True
                    cv2.putText(
                        annotated_frame,
                        "ALERT: DISTANCE/VISION MISMATCH",
                        (20, 80),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 0, 255),
                        2
                    )

        return (1 if person_count > 0 else 0), annotated_frame, spoof_flag

    def process_reading(self, pir: int, dist: float, temp: float, hum: float) -> dict:
        # Phase 1: Self-Calibration Window
        if not self.calibrated:
            self.baseline.append([dist, temp, hum])
            progress = len(self.baseline)
            if progress >= self.calibration_needed:
                arr = np.array(self.baseline)
                self.means = np.mean(arr, axis=0)
                self.stds = np.std(arr, axis=0)
                self.stds[self.stds == 0] = 1e-3

                scaled_baseline = (arr - self.means) / self.stds
                self.iso.fit(scaled_baseline)
                self.calibrated = True
                return {
                    "status": "CALIBRATED_READY",
                    "threat": "NONE",
                    "threat_level": "NONE",
                    "active_alerts": [],
                    "anomaly": False,
                    "frame": None
                }

            return {
                "status": f"CALIBRATING ({progress}/{self.calibration_needed})",
                "threat": "NONE",
                "threat_level": "NONE",
                "active_alerts": [],
                "anomaly": False,
                "frame": None
            }

        # Phase 2: Anomaly Detection (Isolation Forest)
        raw_env = np.array([dist, temp, hum])
        scaled_env = ((raw_env - self.means) / self.stds).reshape(1, -1)
        is_anomaly = 1 if self.iso.predict(scaled_env)[0] == -1 else 0
        anomaly_score = float(self.iso.decision_function(scaled_env)[0])

        # Phase 3: Gated vs. Heartbeat Vision Trigger
        current_time = time.time()
        immediate_trigger = (pir == 1) or (is_anomaly == 1)
        heartbeat_due = (current_time - self.last_vision_time) >= self.heartbeat_interval

        if immediate_trigger or heartbeat_due:
            p_detect, frame, spoof = self._verify_with_vision(dist)
            self.last_person_detected = p_detect
            self.last_annotated_frame = frame
            self.last_spoof_alert = spoof
            self.last_vision_time = current_time
        else:
            # Drain frames to eliminate network stream buffer lag
            if self.camera_ready and self.cap is not None:
                self.cap.grab()

        # Phase 4: Multi-Alert List Evaluation
        active_alerts = []
        if temp >= 45.0:
            active_alerts.append("FIRE_HAZARD")
        elif temp >= 35.0:
            active_alerts.append("HIGH_TEMPERATURE")

        if dist < 60.0:
            active_alerts.append("SPATIAL_PROXIMITY_BREACH")

        if pir == 1:
            active_alerts.append("PIR_MOTION_ACTIVE")

        if self.last_person_detected:
            if "SPATIAL_PROXIMITY_BREACH" in active_alerts or pir == 1:
                active_alerts.append("VERIFIED_INTRUSION")
            else:
                active_alerts.append("UNVERIFIED_HUMAN_IN_VIEW")

        if self.last_spoof_alert:
            active_alerts.append("DEPTH_SPOOF_MISMATCH")

        if is_anomaly:
            active_alerts.append("ENVIRONMENTAL_ANOMALY")

        # Phase 5: Overall Threat Synthesis
        if "FIRE_HAZARD" in active_alerts and "VERIFIED_INTRUSION" in active_alerts:
            overall_threat = "CRITICAL_COMPOUND_HAZARD"
        elif "FIRE_HAZARD" in active_alerts:
            overall_threat = "HAZARD_FIRE"
        elif "VERIFIED_INTRUSION" in active_alerts:
            overall_threat = "CRITICAL_INTRUSION"
        elif "SPATIAL_PROXIMITY_BREACH" in active_alerts:
            overall_threat = "UNIDENTIFIED_OBSTACLE"
        elif "PIR_MOTION_ACTIVE" in active_alerts or "UNVERIFIED_HUMAN_IN_VIEW" in active_alerts:
            overall_threat = "SUSPICIOUS_ACTIVITY"
        elif is_anomaly:
            overall_threat = "ENVIRONMENTAL_DRIFT"
        else:
            overall_threat = "NOMINAL"

        # Returns both 'threat' and 'threat_level' for full compatibility
        return {
            "status": "MONITORING",
            "threat": overall_threat,
            "threat_level": overall_threat,
            "active_alerts": active_alerts,
            "anomaly": bool(is_anomaly),
            "anomaly_score": round(anomaly_score, 3),
            "person_detected": bool(self.last_person_detected),
            "spoof_alert": bool(self.last_spoof_alert),
            "frame": self.last_annotated_frame
        }

    def close(self):
        if self.cap:
            self.cap.release()
            cv2.destroyAllWindows()