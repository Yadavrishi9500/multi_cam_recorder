"""
discovery.py
-------------
Auto-discovers phone/IP cameras on the local WiFi network, so mobile
phones can be added as "plug and play" — no manual IP typing needed.

Works by scanning the local /24 subnet for the common ports used by
phone camera apps:
    - 8080  -> "IP Webcam" (Android)
    - 4747  -> "DroidCam"  (Android / iOS)

For each responsive host, it does a quick HTTP GET to try to confirm
it is actually a camera stream and grab a friendly name.
"""

import concurrent.futures
import socket
import threading
import urllib.request

COMMON_PORTS = {
    8080: {"app": "IP Webcam", "video_path": "/video"},
    4747: {"app": "DroidCam", "video_path": "/video"},
}


def _get_local_subnet():
    """Best-effort guess of this machine's local /24 subnet, e.g. '192.168.1'."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1.0)  # never let a restricted/offline network hang the UI
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        if local_ip and not local_ip.startswith("127."):
            return ".".join(local_ip.split(".")[:3])
    except Exception:
        pass

    # Fallback: use the hostname's own resolved IP (works even with no
    # internet route, e.g. isolated/offline LAN or a locked-down sandbox)
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        if local_ip and not local_ip.startswith("127."):
            return ".".join(local_ip.split(".")[:3])
    except Exception:
        pass
    return None


def _probe_host(ip, port, meta, timeout=0.3):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            if sock.connect_ex((ip, port)) != 0:
                return None
    except Exception:
        return None

    # Port is open — try a light HTTP confirmation (non-fatal if it fails)
    display_name = f"{meta['app']} @ {ip}:{port}"
    try:
        req = urllib.request.Request(f"http://{ip}:{port}/", method="GET")
        with urllib.request.urlopen(req, timeout=0.6) as resp:
            body = resp.read(400).decode(errors="ignore").lower()
            if "ip webcam" in body:
                display_name = f"IP Webcam phone @ {ip}:{port}"
            elif "droidcam" in body:
                display_name = f"DroidCam phone @ {ip}:{port}"
    except Exception:
        pass  # port open but no HTTP root — still report it, just generic name

    return {
        "ip": ip,
        "port": port,
        "app": meta["app"],
        "name": display_name,
        "source_url": f"http://{ip}:{port}{meta['video_path']}",
    }


def _get_local_subnet_bounded(timeout=2.0):
    """Runs _get_local_subnet on a daemon thread so an unusual network stack
    (proxies/firewalls that silently swallow packets instead of refusing)
    can never hang the caller beyond `timeout` seconds."""
    box = {}

    def _worker():
        box["subnet"] = _get_local_subnet()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout)
    return box.get("subnet")


def discover_phone_cameras(max_workers=80, overall_timeout=8.0):
    """Scan the local subnet for phone camera apps. Returns a list of dicts.

    Bounded by overall_timeout so a restricted/offline network (or a
    locked-down sandbox with no LAN access) can never hang the dashboard —
    it just returns whatever was found (possibly nothing) within the limit.
    """
    subnet = _get_local_subnet_bounded(timeout=2.0)
    if not subnet:
        return []

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        tasks = [
            executor.submit(_probe_host, f"{subnet}.{host}", port, meta)
            for host in range(1, 255)
            for port, meta in COMMON_PORTS.items()
        ]
        try:
            for future in concurrent.futures.as_completed(tasks, timeout=overall_timeout):
                res = future.result()
                if res:
                    results.append(res)
        except concurrent.futures.TimeoutError:
            pass  # return whatever we found so far rather than hang

    results.sort(key=lambda r: r["ip"])
    return results
