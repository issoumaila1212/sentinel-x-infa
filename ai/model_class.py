# model_class.py
import time
import cv2
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from ultralytics import YOLO


class SentinelAI:
    def __init__(
        self,
        calibration_samples: int = 15,
        stream_source=None,
        idle_heartbeat: float = 5.0,
        alarm_hold_duration: float = 10.0,
    ):
        # 1. Calibration Configuration
        self.calibration_needed = calibration_samples
        self.baseline = []
        self.calibrated = False
        self.means = None
        self.stds = None

        # 2. Machine Learning Models
        self.iso = IsolationForest(contamination=0.05, random_state=42)
        self.rf = RandomForestClassifier(n_estimators=30, random_state=42)
        self._init_rf()

        # 3. Vision Pipeline
        self.stream_source = stream_source
        self.cap = None
        self.yolo = None
        self.camera_ready = False

        # 4. Adaptive Polling & Hysteresis State
        self.idle_heartbeat = idle_heartbeat          # 5.0s scan when calm
        self.burst_interval = 0.1                     # ~10 FPS burst tracking when active
        self.alarm_hold_duration = alarm_hold_duration  # 10.0s retention cooldown

        self.last_vision_time = 0.0
        self.last_detection_timestamp = 0.0
        self.is_tracking = False

        self.last_person_detected = 0
        self.last_annotated_frame = None
        self.last_spoof_alert = False

        if stream_source is not None:
            self._setup_camera(stream_source)

    def _setup_camera(self, source):
        print(f"[VISION] Initializing video source: {source}")
        self.cap = cv2.VideoCapture(source)
        if self.cap.isOpened():
            self.yolo = YOLO("yolov8n.pt")
            self.camera_ready = True
            print("[VISION] YOLOv8n initialized successfully.")
        else:
            print("[VISION WARNING] Failed to access video source. Operating in telemetry-only mode.")

    def _init_rf(self):
        # Feature vector: [dist, temp, hum, is_anomaly, person_detected]
        X = [
            [220.0, 21.5, 50.0, 0, 0],  # NOMINAL
            [ 45.0, 22.5, 51.0, 1, 0],  # UNIDENTIFIED_OBSTACLE
            [220.0, 21.5, 50.0, 0, 1],  # SUSPICIOUS_PRESENCE
            [ 45.0, 22.5, 51.0, 1, 1],  # CRITICAL_INTRUSION
            [220.0, 50.0, 15.0, 1, 0],  # HAZARD
            [220.0, 50.0, 15.0, 1, 1],  # HAZARD
        ]
        y = [
            "NOMINAL",
            "UNIDENTIFIED_OBSTACLE",
            "SUSPICIOUS_PRESENCE",
            "CRITICAL_INTRUSION",
            "HAZARD",
            "HAZARD",
        ]
        self.rf.fit(X, y)

    def _verify_with_vision(self, dist_cm: float):
        """Fetches the latest video frame, runs YOLO person inference, and applies anti-spoof checks."""
        if not self.camera_ready or self.cap is None:
            return self.last_person_detected, self.last_annotated_frame, self.last_spoof_alert

        ret, frame = self.cap.read()
        if not ret:
            return self.last_person_detected, self.last_annotated_frame, self.last_spoof_alert

        frame_resized = cv2.resize(frame, (640, 480))
        # Class 0 corresponds to 'person' in the COCO dataset
        results = self.yolo(frame_resized, classes=[0], conf=0.5, verbose=False)
        boxes = results[0].boxes
        person_count = len(boxes)
        annotated_frame = results[0].plot()

        spoof_flag = False
        if person_count > 0:
            for b in boxes:
                _, y1, _, y2 = map(int, b.xyxy[0])
                box_h = y2 - y1
                # If bounding box is massive (>280px tall) but the distance sensor reads far (>180cm)
                if box_h > 280 and dist_cm > 180.0:
                    spoof_flag = True
                    cv2.putText(
                        annotated_frame,
                        "DEPTH/VISION SPOOF WARNING",
                        (20, 80),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 0, 255),
                        2,
                    )

        return (1 if person_count > 0 else 0), annotated_frame, spoof_flag

    def process_reading(self, dist: float, temp: float, hum: float, pir: int = 0) -> dict:
        """
        Ingests telemetry metrics, updates anomaly models, schedules adaptive vision,
        and returns an aggregated multi-threat assessment.
        """
        # ==========================================
        # Phase 1: Dynamic Baseline Calibration
        # ==========================================
        if not self.calibrated:
            self.baseline.append([dist, temp, hum])
            progress = len(self.baseline)

            if progress >= self.calibration_needed:
                arr = np.array(self.baseline)
                self.means = np.mean(arr, axis=0)
                self.stds = np.std(arr, axis=0)
                self.stds[self.stds == 0] = 1e-3  # Avoid divide-by-zero on steady telemetry

                scaled_baseline = (arr - self.means) / self.stds
                self.iso.fit(scaled_baseline)
                self.calibrated = True

                return {
                    "status": "CALIBRATED_READY",
                    "threat": "NONE",
                    "threat_level": "NONE",
                    "active_alerts": [],
                    "anomaly": False,
                    "anomaly_score": 0.0,
                    "person_detected": False,
                    "tracking_mode": False,
                    "cooldown_remaining_sec": 0.0,
                    "frame": None,
                }

            return {
                "status": f"CALIBRATING ({progress}/{self.calibration_needed})",
                "threat": "NONE",
                "threat_level": "NONE",
                "active_alerts": [],
                "anomaly": False,
                "anomaly_score": 0.0,
                "person_detected": False,
                "tracking_mode": False,
                "cooldown_remaining_sec": 0.0,
                "frame": None,
            }

        # ==========================================
        # Phase 2: Anomaly Detection (Isolation Forest)
        # ==========================================
        current_time = time.time()
        raw_env = np.array([dist, temp, hum])
        scaled_env = ((raw_env - self.means) / self.stds).reshape(1, -1)
        is_anomaly = 1 if self.iso.predict(scaled_env)[0] == -1 else 0
        anomaly_score = float(self.iso.decision_function(scaled_env)[0])

        spatial_breach = dist < 60.0
        thermal_spike = temp >= 45.0

        # ==========================================
        # Phase 3: Adaptive Vision Scheduling & Hysteresis
        # ==========================================
        time_since_last_detection = current_time - self.last_detection_timestamp
        in_retention_window = time_since_last_detection < self.alarm_hold_duration

        # Select rate: burst mode (0.1s) when tracking or within cooldown; idle patrol (5.0s) otherwise
        target_interval = self.burst_interval if (self.is_tracking or in_retention_window) else self.idle_heartbeat
        vision_due = (current_time - self.last_vision_time) >= target_interval
        immediate_wake = spatial_breach or (is_anomaly == 1) or thermal_spike

        if vision_due or immediate_wake:
            p_detect, frame, spoof = self._verify_with_vision(dist)
            self.last_vision_time = current_time
            self.last_annotated_frame = frame
            self.last_spoof_alert = spoof

            if p_detect:
                # Human presence verified
                self.last_detection_timestamp = current_time
                self.last_person_detected = 1
                self.is_tracking = True
            else:
                # No human detected in current frame
                if in_retention_window:
                    # Hold previous detection active during cooldown window
                    self.last_person_detected = 1
                    self.is_tracking = True
                else:
                    # Cooldown elapsed: safe return to idle mode
                    self.last_person_detected = 0
                    self.is_tracking = False
        else:
            # Drain video queue during idle periods to prevent frame buffering latency
            if self.camera_ready and self.cap is not None:
                self.cap.grab()

        # ==========================================
        # Phase 4: Deterministic Alert Evaluation
        # ==========================================
        active_alerts = []
        if temp >= 45.0:
            active_alerts.append("FIRE_HAZARD")
        elif temp >= 35.0:
            active_alerts.append("HIGH_TEMPERATURE")

        if spatial_breach:
            active_alerts.append("SPATIAL_PROXIMITY_BREACH")

        if self.last_person_detected:
            if spatial_breach:
                active_alerts.append("VERIFIED_INTRUSION")
            else:
                active_alerts.append("VERIFIED_HUMAN_IN_ROOM")

        if self.last_spoof_alert:
            active_alerts.append("DEPTH_SPOOF_MISMATCH")

        if is_anomaly:
            active_alerts.append("ENVIRONMENTAL_ANOMALY")

        # ==========================================
        # Phase 5: Overall Threat Synthesis
        # ==========================================
        has_fire = "FIRE_HAZARD" in active_alerts
        has_intrusion = "VERIFIED_INTRUSION" in active_alerts
        has_presence = "VERIFIED_HUMAN_IN_ROOM" in active_alerts

        if has_fire and (has_intrusion or has_presence):
            overall_threat = "CRITICAL_COMPOUND_HAZARD"
        elif has_fire:
            overall_threat = "HAZARD_FIRE"
        elif has_intrusion:
            overall_threat = "CRITICAL_INTRUSION"
        elif has_presence:
            overall_threat = "HUMAN_PRESENCE_DETECTED"
        elif "SPATIAL_PROXIMITY_BREACH" in active_alerts:
            overall_threat = "UNIDENTIFIED_OBSTACLE"
        elif is_anomaly:
            overall_threat = "ENVIRONMENTAL_DRIFT"
        else:
            overall_threat = "NOMINAL"

        cooldown_remaining = max(
            0.0, round(self.alarm_hold_duration - time_since_last_detection, 1)
        ) if in_retention_window else 0.0

        return {
            "status": "TRACKING" if self.is_tracking else "MONITORING",
            "threat": overall_threat,
            "threat_level": overall_threat,
            "active_alerts": active_alerts,
            "anomaly": bool(is_anomaly),
            "anomaly_score": round(anomaly_score, 3),
            "person_detected": bool(self.last_person_detected),
            "tracking_mode": self.is_tracking,
            "cooldown_remaining_sec": cooldown_remaining,
            "frame": self.last_annotated_frame,
        }

    def close(self):
        """Releases video capture resources and closes display windows."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        cv2.destroyAllWindows()