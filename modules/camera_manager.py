"""
camera_manager.py
------------------
Handles simultaneous capture from multiple camera sources:
  - USB webcams        (integer index, e.g. 0, 1, 2)
  - IP / RTSP cameras  (rtsp:// URL)
  - Mobile phone cams  (http:// MJPEG URL, e.g. IP Webcam Android app)

Each camera runs in its own background thread continuously grabbing
frames so that all cameras stay "live" and can be sampled at the same
instant by the recorder for synchronized recording.
"""

import cv2
import time
import threading
import queue


class CameraStream:
    """Continuously reads frames from one camera source in a background thread."""

    def __init__(self, cam_id, label, source, reconnect_delay=2.0):
        self.cam_id = cam_id
        self.label = label
        self.source = source
        self.reconnect_delay = reconnect_delay

        self._cap = None
        self._thread = None
        self._running = False
        self._lock = threading.Lock()

        self.latest_frame = None
        self.latest_timestamp = None
        self.frame_count = 0
        self.connected = False
        self.last_error = None

    # ---------------------------------------------------------------
    def _open_capture(self):
        cap = cv2.VideoCapture(self.source)
        # Small buffer size -> lower latency for live sync capture
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return cap

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while self._running:
            self._cap = self._open_capture()
            if not self._cap or not self._cap.isOpened():
                self.connected = False
                self.last_error = f"Could not open source '{self.source}'"
                time.sleep(self.reconnect_delay)
                continue

            self.connected = True
            while self._running:
                ok, frame = self._cap.read()
                if not ok or frame is None:
                    self.connected = False
                    self.last_error = "Frame read failed — attempting reconnect"
                    break
                with self._lock:
                    self.latest_frame = frame
                    self.latest_timestamp = time.time()
                    self.frame_count += 1

            if self._cap:
                self._cap.release()
            if self._running:
                time.sleep(self.reconnect_delay)  # retry loop (reconnect)

    def get_frame(self):
        """Return (frame_copy, timestamp) of the most recent frame, or (None, None)."""
        with self._lock:
            if self.latest_frame is None:
                return None, None
            return self.latest_frame.copy(), self.latest_timestamp

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._cap:
            self._cap.release()


class CameraManager:
    """Owns and coordinates all CameraStream instances.

    Supports dynamic add/remove at runtime so cameras (e.g. mobile phones)
    can be plugged in through the web UI without editing any config file
    or restarting the application.
    """

    def __init__(self, camera_configs=None):
        """
        camera_configs: list of dicts like
            {"id": "cam1", "label": "Front-View", "source": 0, "enabled": True}
        """
        self.streams = {}
        for c in camera_configs or []:
            if not c.get("enabled", True):
                continue
            self.add_camera(c["id"], c["label"], c["source"], start=False)

    # ------------------------------------------------------------------
    def add_camera(self, cam_id, label, source, start=True):
        """Add (or replace) a camera at runtime. Returns the CameraStream."""
        if cam_id in self.streams:
            self.streams[cam_id].stop()
        stream = CameraStream(cam_id=cam_id, label=label, source=source)
        self.streams[cam_id] = stream
        if start:
            stream.start()
        return stream

    def remove_camera(self, cam_id):
        stream = self.streams.pop(cam_id, None)
        if stream:
            stream.stop()
        return stream is not None

    def start_all(self):
        for s in self.streams.values():
            s.start()

    def stop_all(self):
        for s in self.streams.values():
            s.stop()

    def get_all_frames(self):
        """Returns dict: cam_id -> (frame, timestamp)"""
        return {cid: s.get_frame() for cid, s in self.streams.items()}

    def status(self):
        return {
            cid: {
                "label": s.label,
                "source": s.source,
                "connected": s.connected,
                "frame_count": s.frame_count,
                "last_error": s.last_error,
            }
            for cid, s in self.streams.items()
        }

    def to_config_list(self):
        """Serialize current cameras back to config.yaml-style list."""
        return [
            {"id": cid, "label": s.label, "source": s.source, "enabled": True}
            for cid, s in self.streams.items()
        ]


def test_camera_source(source, timeout=4.0):
    """Try opening a camera source and reading one frame. Returns (ok, message)."""
    cap = cv2.VideoCapture(source)
    start = time.time()
    ok = False
    while time.time() - start < timeout:
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                break
        time.sleep(0.2)
    cap.release()
    if ok:
        return True, "Connected"
    return False, "Could not read a frame from this source"
