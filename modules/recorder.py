"""
recorder.py
------------
The core orchestrator: takes N camera streams (>=3) and N sensor readers
(3 sensor "options"), and:

  1. Grabs a synchronized snapshot from every camera at a fixed FPS.
  2. Overlays a label on every frame: camera name + timestamp + frame#.
  3. Writes each camera's labeled frames to its own video file.
  4. Logs one row per synchronized "tick" to master_log.csv containing
     the timestamp + per-camera frame numbers + all current sensor
     readings — so cameras and sensors can be cross-referenced later.
  5. Also logs a dedicated sensor_log.csv with a row every time ANY
     sensor produces a new reading (higher resolution than the tick).

Output layout (per recording session):

    output/
      session_2026-09-13_12-30-00/
        cam1_Front-View.mp4
        cam2_Side-View.mp4
        cam3_Top-View_Mobile.mp4
        master_log.csv
        sensor_log.csv
"""

import cv2
import json
import os
import threading
import time
from datetime import datetime

from modules.data_logger import CSVLogger


def _safe_name(text):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text)


class SyncRecorder:
    def __init__(self, camera_manager, sensor_manager, config):
        self.cam_mgr = camera_manager
        self.sensor_mgr = sensor_manager
        self.cfg = config["recording"]

        self._running = False
        self._thread = None
        self._sensor_log_thread = None

        self.session_dir = None
        self.master_logger = None
        self.sensor_logger = None
        self.video_writers = {}
        self._tick_count = 0
        self._last_sensor_snapshot = {}

    # ------------------------------------------------------------------
    def _make_session_dir(self):
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        name = f"{self.cfg.get('session_name_prefix', 'session')}_{stamp}"
        path = os.path.join(self.cfg.get("output_dir", "output"), name)
        os.makedirs(path, exist_ok=True)
        return path

    def _open_video_writers(self, frame_sizes):
        fourcc = cv2.VideoWriter_fourcc(*self.cfg.get("video_codec", "mp4v"))
        fps = self.cfg.get("fps", 20)
        for cam_id, stream in self.cam_mgr.streams.items():
            w, h = frame_sizes.get(cam_id, (1280, 720))
            fname = f"{cam_id}_{_safe_name(stream.label)}.mp4"
            path = os.path.join(self.session_dir, fname)
            self.video_writers[cam_id] = cv2.VideoWriter(path, fourcc, fps, (w, h))

    def _overlay_label(self, frame, label, timestamp, frame_idx):
        if not self.cfg.get("overlay_label", True):
            return frame
        text1 = f"{label}"
        text2 = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        text3 = f"frame #{frame_idx}"
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (0, 0), (w, 70), (0, 0, 0), -1)
        cv2.putText(frame, text1, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, text2, (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, text3, (10, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        return frame

    # ------------------------------------------------------------------
    def start(self):
        if self._running:
            return
        self.session_dir = self._make_session_dir()

        # Give cameras a moment to deliver a first frame so we know frame size
        time.sleep(1.5)
        frame_sizes = {}
        for cam_id, stream in self.cam_mgr.streams.items():
            frame, _ = stream.get_frame()
            if frame is not None:
                h, w = frame.shape[:2]
                frame_sizes[cam_id] = (w, h)
            else:
                frame_sizes[cam_id] = (1280, 720)  # fallback

        self._open_video_writers(frame_sizes)

        master_fields = ["tick", "timestamp_iso", "timestamp_epoch"]
        for cam_id in self.cam_mgr.streams:
            master_fields.append(f"{cam_id}_frame_idx")
            master_fields.append(f"{cam_id}_connected")
        master_fields.append("sensors_json")

        self.master_logger = CSVLogger(os.path.join(self.session_dir, "master_log.csv"), master_fields)
        self.sensor_logger = CSVLogger(
            os.path.join(self.session_dir, "sensor_log.csv"),
            ["timestamp_iso", "timestamp_epoch", "sensor_id", "label", "data_json"],
        )

        self._running = True
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

        self._sensor_log_thread = threading.Thread(target=self._sensor_log_loop, daemon=True)
        self._sensor_log_thread.start()

        return self.session_dir

    def _record_loop(self):
        fps = self.cfg.get("fps", 20)
        interval = 1.0 / fps
        while self._running:
            tick_start = time.time()
            self._tick_count += 1
            row = {
                "tick": self._tick_count,
                "timestamp_iso": datetime.now().isoformat(),
                "timestamp_epoch": tick_start,
            }

            for cam_id, stream in self.cam_mgr.streams.items():
                frame, ts = stream.get_frame()
                row[f"{cam_id}_connected"] = stream.connected
                row[f"{cam_id}_frame_idx"] = stream.frame_count
                if frame is not None:
                    labeled = self._overlay_label(frame, stream.label, ts or tick_start, stream.frame_count)
                    writer = self.video_writers.get(cam_id)
                    if writer is not None:
                        # Resize safety-net in case a stream changes resolution mid-run
                        target_w = int(writer.get(cv2.CAP_PROP_FRAME_WIDTH)) or labeled.shape[1]
                        target_h = int(writer.get(cv2.CAP_PROP_FRAME_HEIGHT)) or labeled.shape[0]
                        if labeled.shape[1] != target_w or labeled.shape[0] != target_h:
                            labeled = cv2.resize(labeled, (target_w, target_h))
                        writer.write(labeled)

            row["sensors_json"] = json.dumps(self.sensor_mgr.read_all())
            self.master_logger.log(row)

            elapsed = time.time() - tick_start
            time.sleep(max(0.0, interval - elapsed))

    def _sensor_log_loop(self):
        """Logs a fine-grained sensor_log.csv row whenever a sensor's reading changes."""
        last_seen = {}
        while self._running:
            readings = self.sensor_mgr.read_all()
            for sid, data in readings.items():
                ts = data.get("timestamp")
                if ts and last_seen.get(sid) != ts:
                    last_seen[sid] = ts
                    sensor_obj = self.sensor_mgr.sensors.get(sid)
                    self.sensor_logger.log(
                        {
                            "timestamp_iso": datetime.fromtimestamp(ts).isoformat(),
                            "timestamp_epoch": ts,
                            "sensor_id": sid,
                            "label": sensor_obj.label if sensor_obj else sid,
                            "data_json": json.dumps(data),
                        }
                    )
            time.sleep(0.05)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._sensor_log_thread:
            self._sensor_log_thread.join(timeout=3)
        for w in self.video_writers.values():
            w.release()
        if self.master_logger:
            self.master_logger.close()
        if self.sensor_logger:
            self.sensor_logger.close()
        self.video_writers = {}
        return self.session_dir

    @property
    def is_running(self):
        return self._running
