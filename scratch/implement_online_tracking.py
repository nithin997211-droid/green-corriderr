import os
import re
import shutil

scratch_base = r'C:\Users\Bv\.gemini\antigravity\scratch\green_corridor_system'
onedrive_base = r'C:\Users\Bv\OneDrive\Documents\green_corridor_system'

# =========================================================================
# 1. UPDATE BACKEND (backend/main.py)
# =========================================================================
main_path = os.path.join(scratch_base, 'backend', 'main.py')
with open(main_path, 'r', encoding='utf-8') as f:
    main_code = f.read()

# Define Presence models and endpoints
presence_code = '''
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
'''

# Upgrade verify_auth to support Name OR Badge ID
new_verify_auth = '''@app.post("/api/auth/verify")
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
    )'''

if '@app.post("/api/driver/presence")' not in main_code:
    # Insert presence_code before @app.post("/api/auth/verify")
    main_code = main_code.replace('class AuthRequest(BaseModel):', presence_code + '\nclass AuthRequest(BaseModel):')

# Replace verify_auth
old_auth_pattern = re.compile(r'@app\.post\("/api/auth/verify"\)\s*async def verify_auth\(req:\s*AuthRequest\):.*?return JSONResponse\(\s*status_code=401,\s*content=\{[^}]+\}\s*\)', re.DOTALL)
main_code = old_auth_pattern.sub(new_verify_auth, main_code)

with open(main_path, 'w', encoding='utf-8') as f:
    f.write(main_code)

with open(os.path.join(onedrive_base, 'backend', 'main.py'), 'w', encoding='utf-8') as f:
    f.write(main_code)

print('Updated backend/main.py successfully in scratch and onedrive!')

# =========================================================================
# 2. UPDATE DRIVER APP (frontend/driver_app.html)
# =========================================================================
drv_path = os.path.join(scratch_base, 'frontend', 'driver_app.html')
with open(drv_path, 'r', encoding='utf-8') as f:
    drv_code = f.read()

# Update AUTHORIZED_DRIVER_ACCOUNTS with name
new_accounts = '''const AUTHORIZED_DRIVER_ACCOUNTS = [
  { id: '045', name: 'dhyan', pin: '2007', passHash: '2007', label: 'Dhyan (EMT #045)', role: 'AMBULANCE_DRIVER', vehicle: '108 Cardiac ICU', hosp: 'Manipal Hospital' },
  { id: '071', name: 'kishan', pin: '2006', passHash: '2006', label: 'Kishan (Driver #071)', role: 'AMBULANCE_DRIVER', vehicle: 'Stroke Unit 02', hosp: 'Apollo BGS Hospital' },
  { id: '099', name: 'mohan', pin: '2006', passHash: '2006', label: 'Mohan (Officer #099)', role: 'TRAFFIC_OFFICER', vehicle: 'Trauma Unit 03', hosp: 'KR Hospital' },
  { id: '109', name: 'nithin', pin: '2006', passHash: '2006', label: 'Nithin (Driver #109)', role: 'AMBULANCE_DRIVER', vehicle: 'Trauma Unit 03', hosp: 'KR Hospital' }
];'''

drv_code = re.sub(r'const AUTHORIZED_DRIVER_ACCOUNTS = \[.*?\];', new_accounts, drv_code, flags=re.DOTALL)

# Update verifyDriverCredentials to match by ID or Name
new_verify_cred = '''function verifyDriverCredentials(idStr, passStr) {
  if (!idStr || !passStr) return null;
  const input = idStr.trim().toLowerCase();
  const rawPin = passStr.trim();
  if (!input || !rawPin) return null;

  // Match by Badge ID (e.g. '045', '45') OR Driver Name (e.g. 'dhyan', 'kishan')
  const matched = AUTHORIZED_DRIVER_ACCOUNTS.find(a => 
    a.id.toLowerCase() === input ||
    a.id.replace(/^0+/, '') === input.replace(/^0+/, '') ||
    (a.name && a.name.toLowerCase() === input)
  );

  if (!matched) return { error: 'UNAUTHORIZED_ID' };

  const validPins = ['2006', '2007', matched.pin];
  const inputHash = hashPasscode(rawPin);
  const isPinValid = validPins.includes(rawPin) || matched.passHash === inputHash;

  if (!isPinValid) return { error: 'INVALID_PIN' };

  const normId = matched.id;
  return {
    id: normId,
    name: matched.name,
    passHash: matched.passHash,
    label: matched.label || `Driver #${normId}`,
    role: matched.role || 'DRIVER'
  };
}'''

drv_code = re.sub(r'function verifyDriverCredentials\(idStr,\s*passStr\)\s*\{.*?^\}', new_verify_cred, drv_code, flags=re.DOTALL | re.MULTILINE)

# Presence reporting function in driver_app.html
presence_reporter = '''
function reportPresence(isOnline) {
  const dId = getLoggedInDriverId() || (inMemoryDriverUser ? inMemoryDriverUser.id : null);
  const dName = inMemoryDriverUser ? (inMemoryDriverUser.name || inMemoryDriverUser.label) : null;
  if (!dId) return;

  const payload = {
    badge_id: dId,
    driver_name: dName,
    is_online: isOnline
  };

  const url = (location.protocol === 'file:') ? 'http://localhost:8000/api/driver/presence' : '/api/driver/presence';
  try {
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true
    }).catch(() => {});
  } catch(e) {}
}

window.addEventListener('beforeunload', () => {
  reportPresence(false);
});
'''

if 'function reportPresence' not in drv_code:
    drv_code = drv_code.replace('function loginSuccess(authRecord) {', presence_reporter + '\nfunction loginSuccess(authRecord) {')

# Hook reportPresence into loginSuccess and logoutDriver
drv_code = drv_code.replace('showToast(`✅ Access Granted: ${authRecord.label', 'reportPresence(true);\n  showToast(`✅ Access Granted: ${authRecord.label')
drv_code = drv_code.replace('function logoutDriver() {', 'function logoutDriver() {\n  reportPresence(false);')

# Also check input placeholder to guide user
drv_code = drv_code.replace('placeholder="Enter Assigned Duty ID"', 'placeholder="Duty ID (045) or Name (dhyan)"')
drv_code = drv_code.replace('placeholder="Enter Security Passcode / PIN"', 'placeholder="PIN (2007 or 2006)"')

with open(drv_path, 'w', encoding='utf-8') as f:
    f.write(drv_code)

with open(os.path.join(onedrive_base, 'frontend', 'driver_app.html'), 'w', encoding='utf-8') as f:
    f.write(drv_code)

print('Updated driver_app.html successfully in scratch and onedrive!')

# =========================================================================
# 3. UPDATE SIMULATION DASHBOARD (frontend/index.html)
# =========================================================================
sim_path = os.path.join(scratch_base, 'frontend', 'index.html')
with open(sim_path, 'r', encoding='utf-8') as f:
    sim_code = f.read()

# Add online drivers pill in top bar if not present
online_pill_html = '<span id="onlineDriversPill" class="meta-badge" style="border-color:rgba(16,185,129,0.3); background:rgba(16,185,129,0.08);"><span class="status-pulse-dot" style="margin-right:4px;"></span>CREW: <span id="onlineCrewCount" style="color:var(--emerald);font-weight:700;">0 STANDBY</span></span>'

if 'id="onlineDriversPill"' not in sim_code:
    sim_code = sim_code.replace('<span class="meta-badge">STANDARD: IRC:67-2012 LHT</span>', online_pill_html + '\n          <span class="meta-badge">STANDARD: IRC:67-2012 LHT</span>')

# Add JS polling and WebSocket presence listener in index.html
presence_poll_js = '''
// ---------------------------------------------------------------------------
// Online Drivers / Active Crew Real-Time Tracking
// ---------------------------------------------------------------------------
let cachedOnlineCrew = [];

function updateOnlineCrewUI(drivers) {
  cachedOnlineCrew = drivers || [];
  const count = cachedOnlineCrew.length;
  const countEl = document.getElementById('onlineCrewCount');
  const pillEl = document.getElementById('onlineDriversPill');
  if (!countEl) return;

  if (count > 0) {
    const names = cachedOnlineCrew.map(d => `${d.driver_name || ('#' + d.badge_id)}`).join(', ');
    countEl.textContent = `${count} ON DUTY (${names})`;
    countEl.style.color = 'var(--emerald)';
    if (pillEl) {
      pillEl.style.borderColor = 'rgba(16,185,129,0.5)';
      pillEl.style.background = 'rgba(16,185,129,0.14)';
      pillEl.title = 'Active on-duty emergency drivers connected right now';
    }
  } else {
    countEl.textContent = '0 STANDBY';
    countEl.style.color = 'var(--tech-blue)';
    if (pillEl) {
      pillEl.style.borderColor = 'var(--border)';
      pillEl.style.background = 'transparent';
      pillEl.title = 'No active driver consoles logged in right now';
    }
  }
}

// Poll online drivers every 3 seconds
setInterval(() => {
  const url = (location.protocol === 'file:') ? 'http://localhost:8000/api/driver/online' : '/api/driver/online';
  fetch(url, { cache: 'no-store' })
    .then(r => r.json())
    .then(data => {
      if (data && Array.isArray(data.online_drivers)) {
        updateOnlineCrewUI(data.online_drivers);
      }
    })
    .catch(() => {});
}, 3000);
'''

if 'function updateOnlineCrewUI' not in sim_code:
    sim_code = sim_code.replace('// ---------------------------------------------------------------------------', presence_poll_js + '\n// ---------------------------------------------------------------------------', 1)

with open(sim_path, 'w', encoding='utf-8') as f:
    f.write(sim_code)

with open(os.path.join(onedrive_base, 'frontend', 'index.html'), 'w', encoding='utf-8') as f:
    f.write(sim_code)

print('Updated index.html successfully in scratch and onedrive!')
print('ALL ONLINE TRACKING IMPLEMENTED CLEANLY!')
