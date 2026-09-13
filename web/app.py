"""
web/app.py
-----------
Plug-and-play browser dashboard:
  - "Setup" screen: scan WiFi for phone cameras (one click add), add
    USB/RTSP cameras, turn sensors on/off and pick real vs simulated.
  - Live MJPEG preview of every added camera angle.
  - Live sensor readings (clearly marked when simulated).
  - Start / Stop recording.
  - All changes are saved back into config.yaml automatically, so the
    app remembers your setup next time you run it — no manual editing
    needed on this PC or a new one.

Run with:
    python web/app.py
Then open:  http://localhost:5000
"""

import os
import sys
import threading
import time
import webbrowser

import cv2
import yaml
from flask import Flask, Response, jsonify, render_template, request

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.camera_manager import CameraManager, test_camera_source
from modules.sensor_manager import SensorManager, list_serial_ports
from modules.recorder import SyncRecorder
from modules.discovery import discover_phone_cameras

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(APP_DIR)
CONFIG_PATH = os.path.join(ROOT_DIR, "config.yaml")
_config_lock = threading.Lock()

app = Flask(__name__)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.setdefault("recording", {})
    cfg["recording"].setdefault("output_dir", "output")
    cfg["recording"]["output_dir"] = os.path.join(ROOT_DIR, cfg["recording"]["output_dir"]) \
        if not os.path.isabs(cfg["recording"]["output_dir"]) else cfg["recording"]["output_dir"]
    cfg.setdefault("cameras", [])
    cfg.setdefault("sensors", [])
    return cfg


def save_config():
    """Persist current in-memory camera/sensor state back to config.yaml."""
    with _config_lock:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        cfg["cameras"] = cam_mgr.to_config_list()
        cfg["sensors"] = sensor_mgr.to_config_list()
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, sort_keys=False)


CONFIG = load_config()
cam_mgr = CameraManager(CONFIG.get("cameras", []))
sensor_mgr = SensorManager(CONFIG.get("sensors", []))
cam_mgr.start_all()

recorder = SyncRecorder(cam_mgr, sensor_mgr, CONFIG)


# ======================================================================
# Pages
# ======================================================================
@app.route("/")
def index():
    return render_template("index.html")


# ======================================================================
# Status (polled every second by the dashboard)
# ======================================================================
@app.route("/api/status")
def api_status():
    return jsonify(
        {
            "cameras": cam_mgr.status(),
            "sensors": {
                sid: {**meta, "reading": (sensor_mgr.sensors[sid].read_latest() if sid in sensor_mgr.sensors else {})}
                for sid, meta in sensor_mgr.status().items()
            },
            "recording": recorder.is_running,
            "session_dir": recorder.session_dir,
        }
    )


# ======================================================================
# Camera management (add / remove / discover)
# ======================================================================
@app.route("/api/cameras/discover")
def api_discover_cameras():
    """Scan the local WiFi network for phone camera apps (IP Webcam / DroidCam).
    Hard-bounded so a weird/locked-down network can never hang this request."""
    box = {"found": []}

    def _worker():
        box["found"] = discover_phone_cameras()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=12.0)

    existing_sources = {str(s.source) for s in cam_mgr.streams.values()}
    for f in box["found"]:
        f["already_added"] = f["source_url"] in existing_sources
    return jsonify({"devices": box["found"]})


@app.route("/api/cameras/test", methods=["POST"])
def api_test_camera():
    data = request.get_json(force=True)
    source = data.get("source")
    if isinstance(source, str) and source.isdigit():
        source = int(source)
    ok, message = test_camera_source(source, timeout=4.0)
    return jsonify({"ok": ok, "message": message})


@app.route("/api/cameras/add", methods=["POST"])
def api_add_camera():
    data = request.get_json(force=True)
    cam_id = data.get("id") or f"cam_{int(time.time() * 1000)}"
    label = data.get("label") or cam_id
    source = data.get("source")
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    cam_mgr.add_camera(cam_id, label, source, start=True)
    save_config()
    return jsonify({"ok": True, "id": cam_id})


@app.route("/api/cameras/remove", methods=["POST"])
def api_remove_camera():
    data = request.get_json(force=True)
    cam_id = data.get("id")
    removed = cam_mgr.remove_camera(cam_id)
    save_config()
    return jsonify({"ok": removed})


def _mjpeg_generator(cam_id):
    while True:
        stream = cam_mgr.streams.get(cam_id)
        if stream is None:
            break
        frame, _ = stream.get_frame()
        if frame is None:
            time.sleep(0.15)
            continue
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")
        time.sleep(0.03)


@app.route("/video_feed/<cam_id>")
def video_feed(cam_id):
    return Response(_mjpeg_generator(cam_id), mimetype="multipart/x-mixed-replace; boundary=frame")


# ======================================================================
# Sensor management
# ======================================================================
@app.route("/api/sensors/ports")
def api_sensor_ports():
    return jsonify({"ports": list_serial_ports()})


@app.route("/api/sensors/configure", methods=["POST"])
def api_configure_sensor():
    data = request.get_json(force=True)
    cfg = sensor_mgr.configure_sensor(
        sensor_id=data["id"],
        sensor_type=data["type"],
        label=data.get("label", data["id"]),
        enabled=bool(data.get("enabled", False)),
        simulate=bool(data.get("simulate", True)),
        port=data.get("port") or None,
        baudrate=int(data.get("baudrate", 9600)),
        poll_hz=float(data.get("poll_hz", 2)),
    )
    save_config()
    return jsonify({"ok": True, "config": cfg})


# ======================================================================
# Recording control
# ======================================================================
@app.route("/api/start", methods=["POST"])
def api_start():
    if not recorder.is_running:
        session_dir = recorder.start()
        return jsonify({"ok": True, "session_dir": session_dir})
    return jsonify({"ok": False, "message": "Already recording"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    if recorder.is_running:
        session_dir = recorder.stop()
        return jsonify({"ok": True, "session_dir": session_dir})
    return jsonify({"ok": False, "message": "Not currently recording"})


def _open_browser_later():
    time.sleep(1.2)
    try:
        webbrowser.open("http://localhost:5000")
    except Exception:
        pass


if __name__ == "__main__":
    threading.Thread(target=_open_browser_later, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
