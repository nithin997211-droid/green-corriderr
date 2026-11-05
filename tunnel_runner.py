import subprocess
import time
import re
import urllib.request
import json
import sys
import os
import threading

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
active_public_url = None
keepalive_started = False

def keepalive_worker():
    global active_public_url
    while True:
        url = active_public_url
        if url:
            try:
                # Active bidirectional ping through the tunnel every 15 seconds
                req = urllib.request.Request(
                    f"{url}/api/status",
                    headers={"User-Agent": "GreenCorridorKeepAlive/1.0", "Bypass-Tunnel-Reminder": "true"}
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    pass
            except Exception:
                pass
        time.sleep(15)

def register_tunnel_with_backend(public_url):
    global active_public_url, keepalive_started
    active_public_url = public_url
    driver_url = f"{public_url}/driver"

    if not keepalive_started:
        keepalive_started = True
        threading.Thread(target=keepalive_worker, daemon=True).start()

    for _ in range(5):
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8000/api/public-tunnel",
                data=json.dumps({"url": public_url}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=3)
            break
        except Exception:
            time.sleep(1)

    print("\n" + "=" * 76, flush=True)
    print("  🟢 PUBLIC INTERNET ACCESS ACTIVE (UNBLOCKED FOR ALL INDIAN ISPS)", flush=True)
    print("=" * 76, flush=True)
    print(f"  🌐 Public Desktop Simulation : {public_url}", flush=True)
    print(f"  📱 Mobile Driver App URL    : {driver_url}", flush=True)
    print("=" * 76, flush=True)
    print("  👉 Anyone on ANY computer or mobile phone (Jio, Airtel, Vi, Wi-Fi) can open:", flush=True)
    print(f"     Desktop Simulation : {public_url}", flush=True)
    print(f"     Driver Mobile App  : {driver_url}", flush=True)
    print("=" * 76 + "\n", flush=True)

def run_public_tunnel():
    print("=" * 76, flush=True)
    print("  GREEN CORRIDOR: SECURE GLOBAL GATEWAY (PERSISTENT CLOUD TUNNEL)", flush=True)
    print("  Connecting to secure public gateway via OpenSSH (localhost.run)...", flush=True)
    print("=" * 76, flush=True)

    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "TCPKeepAlive=yes",
        "-o", "ServerAliveInterval=10",
        "-o", "ServerAliveCountMax=3",
        "-o", "ExitOnForwardFailure=yes",
        "-R", "80:127.0.0.1:8000",
        "nokey@localhost.run"
    ]

    while True:
        try:
            proc = subprocess.Popen(
                ssh_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            public_url = None

            while proc.poll() is None:
                line = proc.stdout.readline()
                if not line:
                    break
                line_str = line.strip()
                if "tunneled with tls" in line_str.lower() or "lhr.life" in line_str or "lhr.pro" in line_str:
                    match = re.search(r"https://[^\s]+\.lhr\.(?:life|pro)", line_str)
                    if match:
                        public_url = match.group(0)
                        register_tunnel_with_backend(public_url)

            proc.wait()
            print("[WARN] Tunnel session closed. Instantly reconnecting in 2 seconds...", flush=True)
            time.sleep(2)
        except Exception as e:
            print(f"[ERR] Tunnel error: {e}. Retrying in 3 seconds...", flush=True)
            time.sleep(3)

def run_tunnel():
    run_public_tunnel()

if __name__ == "__main__":
    run_tunnel()
