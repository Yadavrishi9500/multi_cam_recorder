# Rig Control — Multi-Camera + Multi-Sensor Synchronized Recorder

**Plug-and-play** software: koi bhi PC/laptop par chala do, browser dashboard
khulega, jahan se tum **3 mobile phones (ya USB/IP cameras)** ek click me
add kar sakte ho, **3 sensors** me se jo chaho enable kar sakte ho — koi
config file hand-edit karne ki zaroorat nahi.

Sab kuch synchronized timestamps ke saath record + label + log hota hai,
taaki baad me camera aur sensor data ko match kiya ja sake.

---

## 1. Ek baar install karo

**Windows:** `start_windows.bat` par double-click karo (Python already installed hona chahiye — https://python.org se le lo agar nahi hai).

**Mac / Linux:**
```bash
bash start_mac_linux.sh
```

Ye script khud dependencies install karega aur dashboard start karke
browser me automatically khol dega: **http://localhost:5000**

(Manually chalana ho to: `pip install -r requirements.txt` phir `python web/app.py`)

---

## 2. Dashboard me "Setup" tab kholo

### Cameras add karna (3 mobile phones):

1. Har phone me **"IP Webcam"** app install karo (Android, Play Store pe free
   milega). iPhone ke liye "DroidCam" ya similar app use karo.
2. App khol ke **"Start server"** dabao — screen par ek URL dikhega jaise
   `http://192.168.1.15:8080`.
3. **Important:** Sab phones aur ye PC **same WiFi** par hone chahiye.
4. Dashboard ke Setup tab me **"Scan network for phones"** button dabao —
   automatically dhoond lega aur ek click me "Add this phone" kar dega.
   (Agar scan kuch na dikhaye to source box me manually URL daal ke
   "Test connection" phir "Add camera" dabao.)
5. Yehi 3 baar karo — teeno phones add ho jayenge, alag-alag labels do
   jaise "Front-View", "Side-View", "Top-View".

USB webcam ya IP/RTSP camera bhi isi form se add ho jate hain — bas
source me `0` (USB index) ya `rtsp://...` URL daal do.

### Sensors choose karna (3 options):

Setup tab me 3 sensor slots dikhenge, har ek me dropdown se type choose
karo:
- **Environmental** — Temperature / Humidity / Pressure
- **Motion** — Accelerometer/Gyro + GPS
- **Custom** — koi bhi Arduino jo JSON bhejta ho, bina code badle

Jis sensor ko use karna hai uspe **"Enabled"** checkbox on karo:
- Agar abhi hardware nahi hai to **"Simulate"** ON rakho — demo data
  milega, clearly **"SIMULATED"** label ke saath (real data se confuse
  nahi hoga).
- Real hardware (Arduino/ESP32) available ho to **"Simulate"** OFF karo
  aur dropdown se COM port choose karo (auto-detect hota hai).

**"Save"** dabao — turant effect hoga, dashboard automatically live
readings dikhana start kar dega.

---

## 3. Recording start/stop

Top-right corner me **"Start recording"** button — sabhi added cameras +
enabled sensors ek saath, synchronized, record hone lagenge. **"Stop
recording"** dabate hi session save ho jayega.

---

## 4. Output kahan milega

```
output/
  session_2026-09-13_12-30-00/
    <camera-id>_Front-View.mp4      <- labeled video (name+timestamp burnt in)
    <camera-id>_Side-View.mp4
    <camera-id>_Top-View.mp4
    master_log.csv                  <- har tick: sabhi camera frame#s + sabhi sensor readings, ek row me
    sensor_log.csv                  <- fine-grained, har sensor reading ka alag row
```

Dono CSV files me epoch timestamp hai, isliye video frames aur sensor
data ko baad me precisely match kiya ja sakta hai.

---

## 5. Doosre PC/Laptop par use karna

Poora folder copy karo (ya zip share karo), waha `start_windows.bat`
(Windows) ya `start_mac_linux.sh` (Mac/Linux) chala do. Dependencies
khud install ho jayengi, config.yaml bhi khud ban jayega — same Setup
flow se cameras/sensors add karo, bas.

---

## Troubleshooting

- **Phone scan me kuch nahi mil raha?** — Phone aur PC same WiFi par
  hain confirm karo, IP Webcam app me "Start server" dabaya hai confirm
  karo, aur PC ka firewall local network requests block to nahi kar
  raha check karo.
- **Camera "CONNECTING" hi dikha rahi hai, LIVE nahi ho rahi?** — Source
  URL/index galat ho sakta hai; Setup tab me "Test connection" use karo.
- **Sensor panel khaali hai?** — Normal hai jab tak tum Setup se koi
  sensor "Enabled" nahi karte — jaan-boojh kar aisa rakha hai taaki bina
  wajah fake numbers na dikhein.
