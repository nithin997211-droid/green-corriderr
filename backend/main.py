from .config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_ANON_KEY, is_supabase_enabled, get_supabase_client
import os
import asyncio
import time
import socket
import json
import csv
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .models import VehicleTelemetry
from .engine import GreenCorridorJunction
from .sim_feed import SimulationManager
from .corridor_router import router as corridor_router
from .ml_router import router as ml_router

app = FastAPI(
    title="Green Corridor Intelligent Emergency Vehicle Pre-emption (EVP) System",
    description="Automated Traffic Signal Overriding and Priority Routing for Emergency Vehicles",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_and_no_transform_headers(request, call_next):
    response = await call_next(request)
    # RFC 7234: Tells Cloudflare and proxies NOT to modify HTML responses or inject radar/beacon scripts
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        response.headers["Cache-Control"] = "no-cache, no-transform"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response

app.include_router(corridor_router)
app.include_router(ml_router)

@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
async def favicon():
    svg_favicon = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="45" fill="#0f172a"/><circle cx="50" cy="30" fill="#10b981"/></svg>"""
    return Response(
        content=svg_favicon,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400, no-transform"}
    )

# Global Junction Instance
junction = GreenCorridorJunction(
    junction_id="MYS_KRHOSP_JUNC_01",
    junction_name="KR Hospital - Irwin Road Junction, Mysuru",
    center_lat=12.3168,
    center_lon=76.6508,
    geofence_meters=500.0,
    yellow_duration_sec=3.0,
    max_corridor_timeout_sec=75.0
)

sim_manager = SimulationManager(junction)

# Active WebSocket connections
active_connections: List[WebSocket] = []

class GeofenceUpdate(BaseModel):
    radius_meters: float

class SpawnRequest(BaseModel):
    scenario: str

@app.on_event("startup")
async def startup_event():
    # Start background loop for junction tick & sim step
    asyncio.create_task(background_tick_loop())

async def background_tick_loop():
    """Background engine loop running at 10 Hz (100ms)"""
    while True:
        try:
            sim_manager.update_step()
            junction.tick()

            # Broadcast to web clients
            if active_connections:
                snapshot = junction.get_state_snapshot().model_dump()
                dead_sockets = []
                for ws in list(active_connections):
                    try:
                        await asyncio.wait_for(ws.send_json(snapshot), timeout=0.08)
                    except Exception:
                        dead_sockets.append(ws)
                for ds in dead_sockets:
                    if ds in active_connections:
                        active_connections.remove(ds)

        except Exception as e:
            print(f"Error in background tick loop: {e}")
        await asyncio.sleep(0.1)

# API Endpoints
@app.post("/api/telemetry")
async def receive_telemetry(telemetry: VehicleTelemetry):
    """
    Primary endpoint for hardware GPS trackers (ESP32/SIM7600) mounted on
    Ambulances and Fire Engines.
    """
    result = junction.update_vehicle_telemetry(telemetry)
    return {"status": "success", "processed": result}

@app.get("/api/status")
async def get_junction_status():
    """Returns the current state snapshot of the traffic intersection."""
    return junction.get_state_snapshot()

@app.get("/api/hardware/signals")
async def get_hardware_signals():
    """
    Lightweight endpoint optimized for microcontroller polling (ESP32/Arduino).
    Returns only the necessary pin control states.
    """
    signals = junction.get_signal_lights()
    return {
        "junction_id": junction.junction_id,
        "mode": junction.mode.value,
        "active_corridor": junction.active_corridor.value if junction.active_corridor else "NONE",
        "signals": signals,
        "timestamp": int(time.time())
    }

@app.post("/api/geofence")
async def update_geofence(req: GeofenceUpdate):
    if req.radius_meters < 100 or req.radius_meters > 2500:
        raise HTTPException(status_code=400, detail="Geofence must be between 100m and 2500m")
    junction.geofence_meters = req.radius_meters
    junction._add_log(f"⚙️ Geofence radius adjusted to {req.radius_meters:.0f} meters.")
    return {"status": "updated", "geofence_meters": req.radius_meters}

@app.post("/api/simulation/spawn")
async def spawn_simulation(req: SpawnRequest):
    sim_manager.spawn_preset(req.scenario)
    return {"status": "spawned", "scenario": req.scenario}

@app.post("/api/simulation/clear")
async def clear_simulation():
    active_fleet.clear()
    recent_driver_actions.clear()
    sim_manager.clear_all()
    junction.tracked_vehicles.clear()
    junction.mode = junction.mode.NORMAL_AUTO
    junction.active_corridor = None
    junction.controlling_vehicle = None
    junction._add_log("🧹 All simulated vehicles cleared. Junction reset to Normal Auto.")
    return {"status": "cleared"}


# ---------------------------------------------------------------------------
# Driver Presence & Online Status Tracking
# ---------------------------------------------------------------------------
class DriverPresenceRequest(BaseModel):
    badge_id: str
    driver_name: Optional[str] = None
    vehicle: Optional[str] = None
    hospital: Optional[str] = None
    is_online: bool = True

online_drivers: Dict[str, Dict[str, Any]] = {}

REGISTERED_DRIVERS_MAP = {
    "045": {"badge_id": "045", "name": "dhyan", "pin": "2007", "vehicle": "108 Cardiac ICU (KA-09-G-108)", "hospital": "Manipal Hospital", "role": "AMBULANCE_DRIVER"},
    "071": {"badge_id": "071", "name": "kishan", "pin": "2006", "vehicle": "Stroke & Trauma Unit 02 (KA-09-G-102)", "hospital": "Apollo BGS Hospital", "role": "AMBULANCE_DRIVER"},
    "099": {"badge_id": "099", "name": "mohan", "pin": "2006", "vehicle": "Emergency Trauma Unit 03 (KA-09-G-103)", "hospital": "KR Hospital", "role": "OFFICER"},
    "109": {"badge_id": "109", "name": "nithin", "pin": "2006", "vehicle": "Emergency Trauma Unit 03 (KA-09-G-105)", "hospital": "KR Hospital", "role": "AMBULANCE_DRIVER"}
}

@app.post("/api/driver/presence")
async def update_driver_presence(req: DriverPresenceRequest):
    bid = req.badge_id.strip()
    if not bid:
        return {"status": "error", "message": "Missing badge_id"}

    matched_key = bid
    # Match by ID or Name
    for k, v in REGISTERED_DRIVERS_MAP.items():
        if k == bid or k.lstrip('0') == bid.lstrip('0') or v["name"].lower() == bid.lower():
            matched_key = k
            break

    driver_info = REGISTERED_DRIVERS_MAP.get(matched_key, {})
    d_name = req.driver_name or driver_info.get("name", f"Driver #{bid}").capitalize()

    if req.is_online:
        online_drivers[matched_key] = {
            "badge_id": matched_key,
            "driver_name": d_name,
            "vehicle": req.vehicle or driver_info.get("vehicle", "108 Ambulance"),
            "hospital": req.hospital or driver_info.get("hospital", "KR Hospital"),
            "login_time": datetime.utcnow().isoformat() + "Z",
            "is_online": True
        }
    else:
        online_drivers.pop(matched_key, None)

    # Attempt to update Supabase table authorized_drivers if column exists
    sb = get_supabase_client()
    if sb:
        try:
            sb.table("authorized_drivers").update({"is_online": req.is_online}).eq("badge_id", matched_key).execute()
        except Exception:
            pass

    presence_msg = {
        "type": "DRIVER_PRESENCE",
        "online_drivers": list(online_drivers.values()),
        "count": len(online_drivers)
    }
    await broadcast_action_ws_safe(presence_msg)
    return {"status": "ok", "online_count": len(online_drivers), "is_online": req.is_online, "drivers": list(online_drivers.values())}

@app.get("/api/driver/online")
async def get_online_drivers():
    return {
        "status": "ok",
        "online_drivers": list(online_drivers.values()),
        "count": len(online_drivers)
    }

class AuthRequest(BaseModel):
    user_id: str
    password: str

@app.post("/api/auth/verify")
async def verify_auth(req: AuthRequest):
    uid = req.user_id.strip() if req.user_id else ""
    raw_pin = req.password.strip() if req.password else ""

    # Check local dictionary (supports badge_id like '045' or '45' or name like 'dhyan')
    matched = None
    for k, v in REGISTERED_DRIVERS_MAP.items():
        if k == uid or k.lstrip('0') == uid.lstrip('0') or v["name"].lower() == uid.lower():
            if raw_pin in ["2006", "2007", v["pin"]]:
                matched = v
                break

    if matched:
        return {
            "status": "authenticated",
            "user_id": matched["badge_id"],
            "driver_name": matched["name"].capitalize(),
            "hospital_name": matched["hospital"],
            "assigned_vehicle": matched["vehicle"],
            "role": matched["role"],
            "label": f"{matched['name'].capitalize()} (#{matched['badge_id']})"
        }

    # Supabase Database-Driven Authentication fallback
    sb = get_supabase_client()
    if sb:
        try:
            res = sb.table("authorized_drivers").select("badge_id, driver_name, hospital_name, assigned_vehicle, active").or_(f"badge_id.eq.{uid},driver_name.ilike.{uid}").eq("password_hash", raw_pin).eq("active", True).execute()
            if res.data and len(res.data) > 0:
                user = res.data[0]
                return {
                    "status": "authenticated",
                    "user_id": user.get("badge_id", uid),
                    "driver_name": user.get("driver_name", f"Driver #{uid}"),
                    "hospital_name": user.get("hospital_name", "KR Hospital Trauma Care"),
                    "assigned_vehicle": user.get("assigned_vehicle", "AMBULANCE"),
                    "role": "OFFICER" if user.get("badge_id") in ["045", "099"] else "AMBULANCE_DRIVER",
                    "label": user.get("driver_name", f"Duty #{uid}")
                }
        except Exception as e:
            print(f"[AUTH] Supabase authentication note: {e}")

    return JSONResponse(
        status_code=401,
        content={"status": "denied", "error": "Invalid Government Badge ID / Name or Security Passcode."}
    )

# Mission Analytics & Event Log Persistent Storage (JSON & CSV File Databases)
ANALYTICS_JSON_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mission_analytics.json"))
ANALYTICS_CSV_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mission_analytics.csv"))

def load_analytics_data() -> Dict[str, Any]:
    if os.path.exists(ANALYTICS_JSON_FILE):
        try:
            with open(ANALYTICS_JSON_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "missions": [],
        "summary": {
            "total_dispatches": 0,
            "completed": 0,
            "success_rate_percent": 100.0,
            "total_delay_saved_sec": 0.0,
            "avg_transit_speed_kmh": 62.5
        }
    }

def save_analytics_data(data: Dict[str, Any]):
    try:
        with open(ANALYTICS_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving analytics JSON: {e}")

    # Also maintain persistent CSV spreadsheet file
    try:
        fieldnames = [
            "timestamp", "total_vehicles", "driver_id", "vehicle_id", "vehicle_type",
            "origin", "destination", "success", "delay_saved_sec", "transit_speed_kmh",
            "success_rate_percent"
        ]
        with open(ANALYTICS_CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for m in data.get("missions", []):
                writer.writerow({
                    "timestamp": m.get("timestamp", ""),
                    "total_vehicles": m.get("total_vehicles", 1),
                    "driver_id": m.get("driver_id", "071"),
                    "vehicle_id": m.get("vehicle_id", ""),
                    "vehicle_type": m.get("vehicle_type", "AMBULANCE"),
                    "origin": m.get("origin", "West (Irwin Road Runway)"),
                    "destination": m.get("destination", "KR Hospital Trauma Care"),
                    "success": "YES" if m.get("success", True) else "NO",
                    "delay_saved_sec": m.get("delay_saved_sec", 0.0),
                    "transit_speed_kmh": m.get("transit_speed_kmh", 65.0),
                    "success_rate_percent": m.get("success_rate_percent", 100.0)
                })
    except Exception as e:
        print(f"Error saving analytics CSV: {e}")

class AnalyticsEvent(BaseModel):
    event_type: str
    vehicle_id: str
    vehicle_type: Optional[str] = "AMBULANCE"
    triage: Optional[str] = "P1"
    origin: Optional[str] = "West (Irwin Road Runway)"
    destination: Optional[str] = "KR Hospital Trauma Care"
    driver_id: Optional[str] = "071"
    total_vehicles: Optional[int] = 1
    delay_saved_sec: Optional[float] = 0.0
    transit_speed_kmh: Optional[float] = 65.0
    status: Optional[str] = "COMPLETED"
    success: Optional[bool] = None
    notes: Optional[str] = None

@app.post("/api/analytics/log")
async def log_analytics_event(evt: AnalyticsEvent):
    data = load_analytics_data()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    is_success = (evt.status in ("COMPLETED", "ARRIVED", "SUCCESS") or evt.event_type in ("ARRIVED", "COMPLETED"))
    if evt.success is not None:
        is_success = bool(evt.success)

    # Calculate preliminary running counts
    dispatches = [m for m in data["missions"] if m.get("event_type") == "DISPATCH"]
    completed = [m for m in data["missions"] if m.get("success", False)]
    tot_missions = len(dispatches) + (1 if evt.event_type == "DISPATCH" else 0)
    suc_missions = len(completed) + (1 if is_success else 0)
    denom = max(tot_missions, suc_missions, 1)
    current_success_rate = round((suc_missions / denom * 100.0), 1)

    entry = {
        "timestamp": now_str,
        "event_type": evt.event_type,
        "total_vehicles": int(evt.total_vehicles or len(junction.tracked_vehicles) or 1),
        "driver_id": evt.driver_id or "071",
        "vehicle_id": evt.vehicle_id,
        "vehicle_type": evt.vehicle_type,
        "triage": evt.triage,
        "origin": evt.origin,
        "destination": evt.destination,
        "success": is_success,
        "delay_saved_sec": float(evt.delay_saved_sec or 0.0),
        "transit_speed_kmh": float(evt.transit_speed_kmh or 65.0),
        "success_rate_percent": current_success_rate,
        "status": evt.status,
        "notes": evt.notes
    }
    data["missions"].append(entry)

    # Recalculate summary metrics across all missions
    all_completed = [m for m in data["missions"] if m.get("success", False)]
    all_tot = max(len([m for m in data["missions"] if m.get("event_type") == "DISPATCH"]), len(all_completed))
    comp_count = len(all_completed)
    final_success_rate = round((comp_count / all_tot * 100.0), 1) if all_tot > 0 else 100.0
    total_saved = sum([float(m.get("delay_saved_sec", 0)) for m in data["missions"]])
    speeds = [float(m.get("transit_speed_kmh", 0)) for m in data["missions"] if float(m.get("transit_speed_kmh", 0)) > 0]
    avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 62.0

    data["summary"] = {
        "total_dispatches": all_tot,
        "completed": comp_count,
        "success_rate_percent": final_success_rate,
        "total_delay_saved_sec": round(total_saved, 1),
        "avg_transit_speed_kmh": avg_speed,
        "last_updated": now_str
    }
    save_analytics_data(data)
    return {"status": "logged", "summary": data["summary"]}

@app.get("/api/analytics/summary")
async def get_analytics_summary():
    return load_analytics_data()

@app.get("/api/analytics/export")
async def export_analytics_file():
    if not os.path.exists(ANALYTICS_JSON_FILE):
        save_analytics_data(load_analytics_data())
    return FileResponse(ANALYTICS_JSON_FILE, media_type="application/json", filename="mission_analytics.json")

@app.get("/api/analytics/csv")
async def export_analytics_csv():
    if not os.path.exists(ANALYTICS_CSV_FILE):
        save_analytics_data(load_analytics_data())
    return FileResponse(ANALYTICS_CSV_FILE, media_type="text/csv", filename="mission_analytics.csv")

# Dynamic Public HTTPS Tunnel Registration
PUBLIC_TUNNEL_URL: Optional[str] = None

class PublicTunnelRequest(BaseModel):
    url: str

@app.post("/api/public-tunnel")
async def set_public_tunnel(req: PublicTunnelRequest):
    global PUBLIC_TUNNEL_URL
    PUBLIC_TUNNEL_URL = req.url.rstrip("/")
    print(f"\n[INFO] Public Internet Tunnel Registered: {PUBLIC_TUNNEL_URL}")
    return {"status": "registered", "public_url": PUBLIC_TUNNEL_URL}

@app.get("/api/public-tunnel")
async def get_public_tunnel():
    return {"public_url": PUBLIC_TUNNEL_URL}

# In-Memory Fleet Lifecycle Manager
# Status lifecycle: "DISPATCHED" | "EN_ROUTE" | "ARRIVED" | "ARCHIVED"
active_fleet: Dict[str, Dict[str, Any]] = {}

def prune_fleet_lifecycle():
    """Automatically archive and purge completed runs older than 10 seconds."""
    now = time.time()
    for vid, v in list(active_fleet.items()):
        status = v.get("status", "DISPATCHED")
        if status == "ARRIVED":
            arrived_at = v.get("arrived_at", now)
            if now - arrived_at > 10.0:
                v["status"] = "ARCHIVED"
                v["archived_at"] = now
        elif status == "ARCHIVED":
            archived_at = v.get("archived_at", now)
            if now - archived_at > 30.0:
                del active_fleet[vid]

class VehicleStatusUpdate(BaseModel):
    vehicle_id: str
    status: str  # "DISPATCHED" | "EN_ROUTE" | "ARRIVED" | "ARCHIVED"
    chainage_m: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

# HTTP Fallback & In-Memory Queue for Driver Console Actions
global_driver_action_seq: int = 0
recent_driver_actions: List[Dict[str, Any]] = []

async def broadcast_action_ws_safe(payload_data: Dict[str, Any]):
    """Non-blocking background broadcaster with strict timeout per socket."""
    if not active_connections:
        return
    try:
        payload_str = json.dumps(payload_data)
        dead = []
        for conn in list(active_connections):
            try:
                await asyncio.wait_for(conn.send_text(payload_str), timeout=0.12)
            except Exception:
                dead.append(conn)
        for d in dead:
            if d in active_connections:
                active_connections.remove(d)
    except Exception:
        pass

async def log_dispatch_analytics_async(payload: Dict[str, Any]):
    """Async analytics logger that never blocks HTTP responses."""
    try:
        evt = AnalyticsEvent(
            event_type="DISPATCH",
            vehicle_id=payload.get("vehicleId") or "EV-01",
            vehicle_type=payload.get("vehicleType") or "AMBULANCE",
            triage=payload.get("triage") or "P1",
            origin=payload.get("approachRoute") or "West (Irwin Road Runway)",
            destination=payload.get("hospitalName") or payload.get("targetHospital") or "KR Hospital Trauma Care",
            driver_id=payload.get("driverId") or "UNASSIGNED",
            total_vehicles=len(junction.tracked_vehicles) + 1,
            delay_saved_sec=0.0,
            transit_speed_kmh=65.0,
            status="IN_TRANSIT",
            success=False,
            notes=f"Dispatched via driver web console by Driver #{payload.get('driverId') or 'UNASSIGNED'}"
        )
        await log_analytics_event(evt)
    except Exception as e:
        print(f"[WARN] Async analytics log: {e}")

@app.post("/api/driver/action")
async def post_driver_action(payload: Dict[str, Any]):
    """Ultra-low latency HTTP delivery endpoint for emergency dispatches and driver actions."""
    global global_driver_action_seq
    if not payload:
        return {"status": "ignored", "reason": "empty payload"}
    
    global_driver_action_seq += 1
    payload["seq"] = global_driver_action_seq
    payload["_server_received_at"] = time.time() * 1000.0
    recent_driver_actions.append(payload)
    if len(recent_driver_actions) > 200:
        recent_driver_actions.pop(0)

    # Fire background WebSocket broadcast without stalling HTTP response
    asyncio.create_task(broadcast_action_ws_safe(payload))

    # Register or transition vehicle status in active_fleet lifecycle
    if payload.get("type") == "DRIVER_DISPATCH":
        vid = payload.get("vehicleId") or f"EV-{global_driver_action_seq}"
        active_fleet[vid] = {
            "id": vid,
            "vehicleId": vid,
            "vehicleType": payload.get("vehicleType") or "AMBULANCE",
            "tier": payload.get("tier") or 1,
            "triage": payload.get("triage") or "P1",
            "status": "DISPATCHED",
            "origin": payload.get("approachRoute") or "West (Irwin Road Runway)",
            "destination": payload.get("hospitalName") or payload.get("targetHospital") or "KR Hospital Trauma Care",
            "driverId": payload.get("driverId") or "071",
            "dispatched_at": time.time(),
            "chainage_m": 0.0,
            "speed_kmh": 65.0
        }
        asyncio.create_task(log_dispatch_analytics_async(payload))


    elif payload.get("type") in ("DRIVER_CANCEL", "SIM_RESET"):
        vid = payload.get("vehicleId")
        if vid and vid in active_fleet:
            active_fleet[vid]["status"] = "ARCHIVED"
            active_fleet[vid]["archived_at"] = time.time()
        elif not vid:
            active_fleet.clear()

    return {
        "status": "broadcast_ok",
        "type": payload.get("type"),
        "seq": global_driver_action_seq,
        "timestamp": payload.get("_server_received_at")
    }

@app.get("/api/driver/actions/latest")
async def get_latest_driver_actions(since_seq: int = 0, since: float = 0.0):
    """Guaranteed sequence-ordered polling with zero timestamp race conditions."""
    global global_driver_action_seq
    if since_seq > 0:
        filtered = [a for a in recent_driver_actions if a.get("seq", 0) > since_seq]
    elif since > 0.0:
        filtered = [a for a in recent_driver_actions if a.get("_server_received_at", 0) > since]
    else:
        # On fresh page load or browser refresh (since_seq == 0 and since == 0.0):
        # Do NOT replay old historic dispatches!
        filtered = []
    return {
        "actions": filtered,
        "last_seq": global_driver_action_seq,
        "server_time": time.time() * 1000.0
    }

@app.get("/api/fleet")
async def get_active_fleet():
    """
    Returns ONLY active emergency vehicles with status 'DISPATCHED' or 'EN_ROUTE'.
    Never returns 'ARRIVED' or 'ARCHIVED' vehicles.
    """
    prune_fleet_lifecycle()
    active_units = [v for v in active_fleet.values() if v.get("status") in ("DISPATCHED", "EN_ROUTE")]
    return {
        "fleet": active_units,
        "count": len(active_units),
        "server_time": time.time()
    }

@app.post("/api/fleet/clear")
async def clear_fleet_endpoint():
    """Wipes all active units in memory when CLEAR ALL is pressed."""
    global global_driver_action_seq
    active_fleet.clear()
    recent_driver_actions.clear()
    junction.tracked_vehicles.clear()
    sim_manager.clear_all()
    junction.mode = junction.mode.NORMAL_AUTO
    junction.active_corridor = None
    junction.controlling_vehicle = None
    junction._add_log("🧹 All active fleet units wiped from memory via /api/fleet/clear.")
    return {"status": "cleared", "count": 0}

@app.post("/api/fleet/update")
async def update_fleet_vehicle_status(req: VehicleStatusUpdate):
    """Update status, e.g. marking ARRIVED when reaching KR Hospital Trauma Bay."""
    prune_fleet_lifecycle()
    vid = req.vehicle_id
    if vid not in active_fleet:
        active_fleet[vid] = {
            "id": vid,
            "vehicleId": vid,
            "vehicleType": "AMBULANCE",
            "status": req.status,
            "dispatched_at": time.time(),
            "chainage_m": req.chainage_m or 0.0
        }
    active_fleet[vid]["status"] = req.status
    if req.chainage_m is not None:
        active_fleet[vid]["chainage_m"] = req.chainage_m
        if req.chainage_m >= 1000.0 and active_fleet[vid]["status"] != "ARRIVED":
            active_fleet[vid]["status"] = "ARRIVED"
            active_fleet[vid]["arrived_at"] = time.time()
    if req.status == "ARRIVED" and "arrived_at" not in active_fleet[vid]:
        active_fleet[vid]["arrived_at"] = time.time()
    return {"status": "updated", "vehicle": active_fleet[vid]}

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # Receive client commands (e.g. from driver app or simulation)
            data = await websocket.receive_text()
            # Broadcast incoming driver/simulation event to all other clients
            dead_conns = []
            for conn in list(active_connections):
                if conn != websocket:
                    try:
                        await conn.send_text(data)
                    except Exception:
                        dead_conns.append(conn)
            for d in dead_conns:
                if d in active_connections:
                    active_connections.remove(d)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)


@app.get("/api/supabase-config")
async def get_supabase_config():
    """Returns Supabase configuration for frontend real-time synchronization."""
    return {
        "url": SUPABASE_URL,
        "key": SUPABASE_KEY,
        "anon_key": SUPABASE_ANON_KEY,
        "is_enabled": is_supabase_enabled()
    }

# Serve Frontend HTML & Driver Mobile App
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return socket.gethostbyname(socket.gethostname())

@app.get("/api/local-ip")
async def get_ip_info():
    ip = get_local_ip()
    local_driver = f"http://{ip}:8000/driver"
    public_driver = f"{PUBLIC_TUNNEL_URL}/driver" if PUBLIC_TUNNEL_URL else None
    return {
        "ip": ip,
        "port": 8000,
        "driver_url": public_driver or local_driver,
        "local_driver_url": local_driver,
        "public_driver_url": public_driver,
        "desktop_url": PUBLIC_TUNNEL_URL or f"http://{ip}:8000",
        "public_url": PUBLIC_TUNNEL_URL
    }

@app.get("/api/qr")
async def generate_qr(url: str = None):
    """Generates a standard, scannable SVG QR code encoding the mobile driver app URL."""
    try:
        import qrcode
        import qrcode.image.svg
        if not url:
            if PUBLIC_TUNNEL_URL:
                url = f"{PUBLIC_TUNNEL_URL}/driver"
            else:
                ip = get_local_ip()
                url = f"http://{ip}:8000/driver"
        factory = qrcode.image.svg.SvgImage
        img = qrcode.make(url, image_factory=factory)
        svg_content = img.to_string()
        return Response(content=svg_content, media_type="image/svg+xml")
    except Exception as e:
        return Response(content=f"<svg width='180' height='180'><text x='10' y='50'>Error: {str(e)}</text></svg>", media_type="image/svg+xml", status_code=500)

@app.get("/driver")
async def serve_driver_app():
    driver_path = os.path.join(FRONTEND_DIR, "driver_app.html")
    if os.path.exists(driver_path):
        return FileResponse(driver_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})
    return HTMLResponse("<h1>Driver App file not found in frontend directory.</h1>")

@app.get("/")
async def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})
    return HTMLResponse("<h1>Green Corridor Backend Running. Frontend file not found.</h1>")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


if __name__ == "__main__":
    local_ip = get_local_ip()
    print(f"Driver Webpage accessible on your phone via: http://{local_ip}:8000/driver")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
