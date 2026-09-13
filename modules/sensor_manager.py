"""
sensor_manager.py
------------------
Provides 3 pluggable sensor "options" that can each run over a serial
(USB/UART) connection to an Arduino / ESP32 / RPi, OR in "simulate" mode
(generates realistic fake data) so the whole pipeline can be tested
without any physical hardware attached.

Sensor Option 1 -> EnvironmentalSensor  (Temperature, Humidity, Pressure)
Sensor Option 2 -> MotionSensor         (Accelerometer/Gyro + GPS)
Sensor Option 3 -> CustomSensor         (generic JSON-line passthrough,
                                          for any custom Arduino sketch)

All sensors expose the same interface:
    start(), stop(), read_latest() -> dict, label
so the recorder / web dashboard can treat them polymorphically.
"""

import json
import random
import threading
import time

try:
    import serial  # pyserial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False


class BaseSensor:
    def __init__(self, sensor_id, label, port, baudrate, simulate, poll_hz):
        self.sensor_id = sensor_id
        self.label = label
        self.port = port
        self.baudrate = baudrate
        self.simulate = simulate or not SERIAL_AVAILABLE
        self.poll_interval = 1.0 / max(poll_hz, 0.1)

        self._ser = None
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self.latest_reading = {}
        self.connected = False
        self.last_error = None

    # -- override in subclasses --
    def _simulate_reading(self):
        raise NotImplementedError

    def _parse_line(self, line):
        raise NotImplementedError

    def _open_serial(self):
        if self.simulate:
            return None
        try:
            ser = serial.Serial(self.port, self.baudrate, timeout=1)
            self.connected = True
            self.last_error = None
            return ser
        except Exception as e:
            self.connected = False
            self.last_error = str(e)
            return None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        if self.simulate:
            self.connected = True
            while self._running:
                reading = self._simulate_reading()
                reading["timestamp"] = time.time()
                with self._lock:
                    self.latest_reading = reading
                time.sleep(self.poll_interval)
            return

        # Real hardware mode
        while self._running:
            if self._ser is None:
                self._ser = self._open_serial()
                if self._ser is None:
                    time.sleep(2)
                    continue
            try:
                raw = self._ser.readline().decode(errors="ignore").strip()
                if raw:
                    reading = self._parse_line(raw)
                    if reading:
                        reading["timestamp"] = time.time()
                        with self._lock:
                            self.latest_reading = reading
            except Exception as e:
                self.connected = False
                self.last_error = str(e)
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None
                time.sleep(2)

    def read_latest(self):
        with self._lock:
            return dict(self.latest_reading)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._ser:
            self._ser.close()


# ---------------------------------------------------------------------
# Sensor Option 1: Environmental (Temp / Humidity / Pressure)
# Expected serial line format from Arduino: "temp,humidity,pressure"
#   e.g.  "24.6,55.2,1012.3"
# ---------------------------------------------------------------------
class EnvironmentalSensor(BaseSensor):
    def _simulate_reading(self):
        return {
            "temperature_C": round(22 + random.uniform(-1.5, 1.5), 2),
            "humidity_%": round(50 + random.uniform(-5, 5), 2),
            "pressure_hPa": round(1013 + random.uniform(-3, 3), 2),
        }

    def _parse_line(self, line):
        try:
            temp, hum, pres = line.split(",")
            return {
                "temperature_C": float(temp),
                "humidity_%": float(hum),
                "pressure_hPa": float(pres),
            }
        except Exception:
            return None


# ---------------------------------------------------------------------
# Sensor Option 2: Motion (Accelerometer/Gyro) + GPS
# Expected serial line: "ax,ay,az,gx,gy,gz,lat,lon"
# ---------------------------------------------------------------------
class MotionSensor(BaseSensor):
    def _simulate_reading(self):
        return {
            "accel_x": round(random.uniform(-1, 1), 3),
            "accel_y": round(random.uniform(-1, 1), 3),
            "accel_z": round(9.8 + random.uniform(-0.2, 0.2), 3),
            "gyro_x": round(random.uniform(-5, 5), 2),
            "gyro_y": round(random.uniform(-5, 5), 2),
            "gyro_z": round(random.uniform(-5, 5), 2),
            "lat": round(30.3165 + random.uniform(-0.0005, 0.0005), 6),
            "lon": round(78.0322 + random.uniform(-0.0005, 0.0005), 6),
        }

    def _parse_line(self, line):
        try:
            parts = [float(x) for x in line.split(",")]
            keys = ["accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z", "lat", "lon"]
            return dict(zip(keys, parts))
        except Exception:
            return None


# ---------------------------------------------------------------------
# Sensor Option 3: Custom / Generic sensor
# Expects the Arduino to send a JSON object per line, e.g.:
#   {"light_lux": 340, "sound_db": 52, "gas_ppm": 410}
# This lets the user plug ANY custom sensor without changing this code —
# just make the Arduino sketch print JSON.
# ---------------------------------------------------------------------
class CustomSensor(BaseSensor):
    def _simulate_reading(self):
        return {
            "light_lux": round(random.uniform(100, 800), 1),
            "sound_db": round(random.uniform(30, 70), 1),
            "gas_ppm": round(random.uniform(350, 450), 1),
        }

    def _parse_line(self, line):
        try:
            return json.loads(line)
        except Exception:
            return None


SENSOR_CLASS_MAP = {
    "environmental": EnvironmentalSensor,
    "motion": MotionSensor,
    "custom": CustomSensor,
}


class SensorManager:
    """Owns and coordinates all configured sensors.

    A sensor slot only actually runs (and only ever appears in the
    dashboard / logs) once it has been explicitly enabled — either in
    config.yaml with `enabled: true`, or later through the web UI. This
    avoids the dashboard filling up with meaningless auto-generated demo
    numbers for sensors nobody asked to turn on.
    """

    def __init__(self, sensor_configs):
        self.sensors = {}
        self.meta = {}  # sid -> {enabled, type, port, baudrate, simulate, poll_hz, label}
        for s in sensor_configs or []:
            self.meta[s["id"]] = dict(s)
            if s.get("enabled", False):
                self._start_sensor(s)

    def _start_sensor(self, s):
        cls = SENSOR_CLASS_MAP.get(s["type"])
        if cls is None:
            return
        sensor = cls(
            sensor_id=s["id"],
            label=s["label"],
            port=s.get("port"),
            baudrate=s.get("baudrate", 9600),
            simulate=s.get("simulate", True),
            poll_hz=s.get("poll_hz", 2),
        )
        self.sensors[s["id"]] = sensor
        sensor.start()

    # ------------------------------------------------------------------
    def configure_sensor(self, sensor_id, sensor_type, label, enabled, simulate, port=None, baudrate=9600, poll_hz=2):
        """Create/update/enable/disable a sensor slot at runtime (from the UI)."""
        # stop existing instance if present
        if sensor_id in self.sensors:
            self.sensors[sensor_id].stop()
            del self.sensors[sensor_id]

        cfg = {
            "id": sensor_id,
            "type": sensor_type,
            "label": label,
            "enabled": enabled,
            "simulate": simulate,
            "port": port,
            "baudrate": baudrate,
            "poll_hz": poll_hz,
        }
        self.meta[sensor_id] = cfg

        if enabled:
            self._start_sensor(cfg)
        return cfg

    def start_all(self):
        for s in self.sensors.values():
            s.start()

    def stop_all(self):
        for s in self.sensors.values():
            s.stop()

    def read_all(self):
        """Returns dict: sensor_id -> latest reading dict (only enabled sensors)"""
        return {sid: s.read_latest() for sid, s in self.sensors.items()}

    def status(self):
        """Status for ALL configured slots (enabled or not), for the Setup UI."""
        out = {}
        for sid, cfg in self.meta.items():
            live = self.sensors.get(sid)
            out[sid] = {
                "label": cfg.get("label", sid),
                "type": cfg.get("type"),
                "enabled": cfg.get("enabled", False),
                "simulate": cfg.get("simulate", True),
                "port": cfg.get("port"),
                "connected": live.connected if live else False,
                "last_error": live.last_error if live else None,
            }
        return out

    def to_config_list(self):
        return list(self.meta.values())


def list_serial_ports():
    """List available serial ports on this machine, for the Setup UI dropdown."""
    if not SERIAL_AVAILABLE:
        return []
    try:
        from serial.tools import list_ports
        return [{"device": p.device, "description": p.description} for p in list_ports.comports()]
    except Exception:
        return []
