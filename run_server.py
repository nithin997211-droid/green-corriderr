import sys
import uvicorn
import webbrowser
import threading
import time
import socket

# Force UTF-8 encoding on Windows console to prevent charmap encoding errors
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return socket.gethostbyname(socket.gethostname())

def open_browser():
    time.sleep(1.5)
    print("\n[INFO] Launching Green Corridor Web Dashboard: http://localhost:8000 ...")
    webbrowser.open("http://localhost:8000")

import subprocess
import os

def start_background_tunnel():
    time.sleep(2.0)
    try:
        tunnel_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tunnel_runner.py")
        subprocess.Popen([sys.executable, "-u", tunnel_script])
    except Exception as e:
        print(f"[WARN] Public tunnel background start: {e}")

if __name__ == "__main__":
    local_ip = get_local_ip()
    print("=" * 76)
    print("  GREEN CORRIDOR - EMERGENCY VEHICLE PRE-EMPTION (EVP) SYSTEM")
    print("  Mysuru Smart Traffic Pilot Edition (MCTP / KR Hospital)")
    print("=" * 76)
    print(f"  [LOCAL DASHBOARD]        : http://localhost:8000")
    print(f"  [LOCAL WI-FI DRIVER APP] : http://{local_ip}:8000/driver")
    print(f"  👉 Driver Webpage accessible on your phone via: http://{local_ip}:8000/driver")
    print("  [PUBLIC INTERNET TUNNEL] : Initializing OpenSSH gateway in background...")
    print("=" * 76)
    print("  Starting FastAPI Server on 0.0.0.0:8000 ...\n")
    
    # Auto launch browser in background
    threading.Thread(target=open_browser, daemon=True).start()

    # Auto launch public tunnel in background
    threading.Thread(target=start_background_tunnel, daemon=True).start()

    # Run uvicorn stably in single-process mode
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
