# Rig Control — Multi-Camera + Multi-Sensor Synchronized Recorder

**Plug-and-play** software: Run it on any PC/laptop, and a browser dashboard will open. From there, you can add **3 mobile phones (or USB/IP cameras)** with a single click, and enable whichever of the **3 sensors** you want—no need to hand-edit any config files.

Everything is recorded, labeled, and logged with synchronized timestamps so that the camera and sensor data can be easily matched later.

---

## 1. One-Time Installation

**Windows:** Double-click on `start_windows.bat` (Python must already be installed—download it from [https://python.org](https://python.org) if you don't have it).

**Mac / Linux:**

```bash
bash start_mac_linux.sh

```

This script will automatically install the dependencies, start the dashboard, and open it in your browser: **http://localhost:5000**

(To run it manually: execute `pip install -r requirements.txt`, followed by `python web/app.py`.)

---

## 2. Open the "Setup" Tab in the Dashboard

### Adding Cameras (3 mobile phones):

1. Install the **"IP Webcam"** app on each phone (available for free on the Android Play Store). For iPhones, use "DroidCam" or a similar app.
2. Open the app and tap **"Start server"** — a URL like `[http://192.168.1.15:8080](http://192.168.1.15:8080)` will appear on the screen.
3. **Important:** All phones and the PC must be connected to the **same WiFi network**.
4. Click the **"Scan network for phones"** button in the dashboard's Setup tab—it will automatically find the devices and allow you to "Add this phone" with one click. (If the scan doesn't detect anything, manually enter the URL in the source box, click "Test connection", and then "Add camera".)
5. Repeat this process 3 times to add all three phones. Assign them different labels such as "Front-View", "Side-View", and "Top-View".

USB webcams or IP/RTSP cameras can also be added using this same form—just enter `0` (for the USB index) or the `rtsp://...` URL into the source field.

### Choosing Sensors (3 options):

You will see 3 sensor slots in the Setup tab. Choose the sensor type from the dropdown for each:

* **Environmental** — Temperature / Humidity / Pressure
* **Motion** — Accelerometer/Gyro + GPS
* **Custom** — Any Arduino that sends JSON, without modifying the code

Turn on the **"Enabled"** checkbox for whichever sensor you want to use:

* If you don't have the hardware connected yet, keep **"Simulate"** ON—you will receive demo data, clearly marked with a **"SIMULATED"** label (so it doesn't get confused with real data).
* If real hardware (Arduino/ESP32) is available, turn **"Simulate"** OFF and select the COM port from the dropdown (it auto-detects).

Click **"Save"**—the changes will take effect immediately, and the dashboard will automatically start showing live readings.

---

## 3. Starting/Stopping the Recording

Click the **"Start recording"** button in the top-right corner—all added cameras and enabled sensors will begin recording simultaneously and synchronized. As soon as you click **"Stop recording"**, the session will be saved.

---

## 4. Where to Find the Output

```text
output/
  session_2026-09-13_12-30-00/
    _Front-View.mp4      <- labeled video (name+timestamp burnt in)
    _Side-View.mp4
    _Top-View.mp4
    master_log.csv                  <- every tick: all camera frame#s + all sensor readings in a single row
    sensor_log.csv                  <- fine-grained, separate row for each sensor reading

```

Both CSV files include epoch timestamps, which allows video frames and sensor data to be precisely matched later on.

---

## 5. Using on Another PC/Laptop

Copy the entire folder (or share the zip file), and run `start_windows.bat` (Windows) or `start_mac_linux.sh` (Mac/Linux) on the new machine. Dependencies will install automatically, and the `config.yaml` file will generate on its own—just add your cameras/sensors using the same Setup flow, and you are good to go.

---

## Troubleshooting

* **Scan not finding any phones?** — Confirm that the phone and PC are on the same WiFi network, ensure you tapped "Start server" in the IP Webcam app, and check that your PC's firewall isn't blocking local network requests.
* **Camera is stuck on "CONNECTING" and won't go LIVE?** — The Source URL or index might be incorrect; use "Test connection" in the Setup tab.
* **Sensor panel is empty?** — This is normal until you mark a sensor as "Enabled" in Setup—this is done intentionally so that fake numbers aren't displayed unnecessarily.
