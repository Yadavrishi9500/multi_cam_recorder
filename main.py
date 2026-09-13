"""
main.py
--------
Desktop / CLI entry point.

Usage:
    python main.py                 # run with config.yaml, press ENTER to stop
    python main.py --seconds 30    # auto-stop after 30 seconds
    python main.py --config myconfig.yaml
"""

import argparse
import sys
import time
import yaml

from modules.camera_manager import CameraManager
from modules.sensor_manager import SensorManager
from modules.recorder import SyncRecorder


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Multi-camera + multi-sensor synchronized recorder")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML config file")
    parser.add_argument("--seconds", type=float, default=None, help="Auto-stop after N seconds")
    args = parser.parse_args()

    config = load_config(args.config)

    cameras_cfg = config.get("cameras", [])
    sensors_cfg = config.get("sensors", [])

    enabled_cams = [c for c in cameras_cfg if c.get("enabled", True)]
    print(f"[INFO] {len(enabled_cams)} camera(s) enabled: "
          + ", ".join(f"{c['id']}({c['label']})" for c in enabled_cams))
    print(f"[INFO] {len(sensors_cfg)} sensor(s) configured: "
          + ", ".join(f"{s['id']}[{s['type']}]" for s in sensors_cfg))

    if len(enabled_cams) < 3:
        print("[WARN] Fewer than 3 cameras enabled — edit config.yaml to add more angles.")

    cam_mgr = CameraManager(cameras_cfg)
    sensor_mgr = SensorManager(sensors_cfg)

    print("[INFO] Starting camera streams...")
    cam_mgr.start_all()
    print("[INFO] Starting sensors...")
    sensor_mgr.start_all()

    recorder = SyncRecorder(cam_mgr, sensor_mgr, config)
    session_dir = recorder.start()
    print(f"[INFO] Recording started -> {session_dir}")

    try:
        if args.seconds:
            time.sleep(args.seconds)
        else:
            input("[INFO] Recording... Press ENTER to stop.\n")
    except KeyboardInterrupt:
        pass
    finally:
        print("[INFO] Stopping recorder...")
        recorder.stop()
        cam_mgr.stop_all()
        sensor_mgr.stop_all()
        print(f"[DONE] Session saved at: {session_dir}")


if __name__ == "__main__":
    sys.exit(main())
