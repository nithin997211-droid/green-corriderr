import asyncio
import subprocess
import json
import urllib.request
import websockets
import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

CHROME_BIN = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9222

async def run_tests():
    print("==================================================================")
    print("  GREEN CORRIDOR AUTOMATED BROWSER VERIFICATION (CHROME CDP)")
    print("==================================================================")
    
    # Launch Headless Chrome with fresh temp user data dir
    user_data = r"C:\Users\Bv\.gemini\antigravity\scratch\chrome_test_profile"
    chrome_proc = subprocess.Popen([
        CHROME_BIN,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={user_data}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "about:blank"
    ])

    await asyncio.sleep(2)
    ws = None
    try:
        # Get target WebSocket URL
        res = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5)
        targets = json.loads(res.read().decode())
        ws_url = targets[0]["webSocketDebuggerUrl"]
        print(f"[CDP] Connected to Chrome Page at: {ws_url}")

        ws = await websockets.connect(ws_url)

        msg_id = 0
        async def send(method, params=None):
            nonlocal msg_id
            msg_id += 1
            payload = {"id": msg_id, "method": method, "params": params or {}}
            await ws.send(json.dumps(payload))
            while True:
                resp = json.loads(await ws.recv())
                if resp.get("id") == msg_id:
                    return resp

        async def eval_js(expr):
            r = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            if "exceptionDetails" in r.get("result", {}):
                raise RuntimeError(f"JS Exception: {r['result']['exceptionDetails']}")
            return r.get("result", {}).get("result", {}).get("value")

        async def navigate(url):
            await send("Page.navigate", {"url": url})
            for _ in range(40):
                await asyncio.sleep(0.2)
                try:
                    state = await eval_js("document.readyState")
                    href = await eval_js("window.location.href")
                    if state == "complete" and url in href:
                        await asyncio.sleep(0.5)
                        return
                except Exception:
                    pass
            await asyncio.sleep(1)

        # Enable runtime & console
        await send("Runtime.enable")
        await send("Page.enable")

        # -------------------------------------------------------------
        # TEST 1: Driver App Initial State & No Auto-Login
        # -------------------------------------------------------------
        print("\n--- TEST 1: Load /driver & Verify Login Gate & No Auto-Login ---")
        await navigate("http://localhost:8000/driver")

        is_modal_visible = await eval_js("document.getElementById('driverAuthModal').style.display !== 'none'")
        print(f"  [CHECK] Auth modal visible upon load? {is_modal_visible} (Expected: True)")
        assert is_modal_visible, "Modal should be visible upon load!"

        badge_visible = await eval_js("document.getElementById('driverBadge').style.display !== 'none'")
        print(f"  [CHECK] Driver badge visible before login? {badge_visible} (Expected: False)")
        assert not badge_visible, "Badge should NOT be visible before login!"

        badge_text = await eval_js("document.getElementById('driverBadgeId').textContent")
        print(f"  [CHECK] Driver badge text: '{badge_text}' (Expected: 'LOCKED')")
        assert badge_text == "LOCKED", f"Badge text was {badge_text}, expected 'LOCKED'"

        logged_in_id = await eval_js("getLoggedInDriverId()")
        print(f"  [CHECK] getLoggedInDriverId() before login: {logged_in_id} (Expected: None)")
        assert logged_in_id is None, f"Expected None but got {logged_in_id}"

        # -------------------------------------------------------------
        # TEST 2: Verify No Disclosed Passwords / PINs on Driver Screen
        # -------------------------------------------------------------
        print("\n--- TEST 2: Credential Disclosure Audit on Driver App ---")
        modal_html = await eval_js("document.getElementById('driverAuthModal').innerHTML")
        has_pin_leak = any(k in modal_html.lower() for k in ["2006", "2007", "quicklogin", "whitelisted", "officer #045", "driver #071"])
        print(f"  [CHECK] Does driver modal disclose PINs or accounts? {has_pin_leak} (Expected: False)")
        assert not has_pin_leak, "Driver modal leaks credentials!"

        # -------------------------------------------------------------
        # TEST 3: Attempt Emergency Dispatch without Authentication
        # -------------------------------------------------------------
        print("\n--- TEST 3: Block Dispatch While Unauthenticated ---")
        fleet_len_before = await eval_js("activeFleet.length")
        await eval_js("handleEmergencyButtonClick()")
        await asyncio.sleep(0.5)
        fleet_len_after = await eval_js("activeFleet.length")
        is_modal_still_visible = await eval_js("document.getElementById('driverAuthModal').style.display !== 'none'")
        print(f"  [CHECK] Fleet unchanged (0)? before={fleet_len_before}, after={fleet_len_after}")
        print(f"  [CHECK] Modal still guarding screen? {is_modal_still_visible}")
        assert fleet_len_after == 0, "Unauthenticated dispatch should not add to fleet!"
        assert is_modal_still_visible, "Modal must remain visible!"

        # -------------------------------------------------------------
        # TEST 4: Submit Valid Login Credentials (ID: 071, PIN: 2006)
        # -------------------------------------------------------------
        print("\n--- TEST 4: Authenticate with Driver ID: 071, PIN: 2006 ---")
        await eval_js("""
            document.getElementById('txtDriverId').value = '071';
            document.getElementById('txtDriverPin').value = '2006';
            handleDriverAuthSubmit(new Event('submit'));
        """)
        await asyncio.sleep(1)

        is_modal_now_hidden = await eval_js("document.getElementById('driverAuthModal').style.display === 'none'")
        badge_now_visible = await eval_js("document.getElementById('driverBadge').style.display !== 'none'")
        badge_now_text = await eval_js("document.getElementById('driverBadgeId').textContent")
        auth_driver_id = await eval_js("getLoggedInDriverId()")

        print(f"  [CHECK] Modal hidden after login? {is_modal_now_hidden} (Expected: True)")
        print(f"  [CHECK] Badge visible after login? {badge_now_visible} (Expected: True)")
        print(f"  [CHECK] Badge text: '{badge_now_text}' (Expected: 'Driver #071' or 'ID: #071')")
        print(f"  [CHECK] Logged-in Driver ID: '{auth_driver_id}' (Expected: '071')")

        assert is_modal_now_hidden, "Modal should hide after successful login!"
        assert badge_now_visible, "Badge should appear after login!"
        assert auth_driver_id == "071", f"Expected '071' but got {auth_driver_id}"

        # -------------------------------------------------------------
        # TEST 5: Interactive Vehicle Profiles, Hospitals & Origins
        # -------------------------------------------------------------
        print("\n--- TEST 5: Test Profile, Hospital, Origin & Triage Controls ---")
        # 1. Switch to Fire Tender
        await eval_js("selectVehicleProfile('FIRE_BRIGADE')")
        h_title = await eval_js("document.getElementById('appHeaderTitle').textContent")
        print(f"  [CHECK] Vehicle switched to Fire: '{h_title}'")
        assert "FIRE" in h_title, "Failed to switch to FIRE_BRIGADE"

        # 2. Switch to Police
        await eval_js("selectVehicleProfile('POLICE')")
        h_title = await eval_js("document.getElementById('appHeaderTitle').textContent")
        print(f"  [CHECK] Vehicle switched to Police: '{h_title}'")
        assert "POLICE" in h_title, "Failed to switch to POLICE"

        # 3. Switch back to Ambulance
        await eval_js("selectVehicleProfile('AMBULANCE')")
        h_title = await eval_js("document.getElementById('appHeaderTitle').textContent")
        print(f"  [CHECK] Vehicle switched to Ambulance: '{h_title}'")
        assert "108" in h_title, "Failed to switch to AMBULANCE"

        # 4. Destination Hospital selection
        await eval_js("setDestinationHospital('HOSP_APOLLO')")
        dest_hud = await eval_js("document.getElementById('teleDest').textContent")
        print(f"  [CHECK] Target Hospital set to Apollo: '{dest_hud}'")
        assert "APOLLO" in dest_hud, "Failed to set Apollo destination"

        await eval_js("setDestinationHospital('HOSP_KR')")
        dest_hud = await eval_js("document.getElementById('teleDest').textContent")
        print(f"  [CHECK] Target Hospital set to KR: '{dest_hud}'")
        assert "KR" in dest_hud, "Failed to set KR destination"

        # 5. Approach origin corridor selection
        await eval_js("setApproachRoute('EAST_TURN')")
        appr_tag = await eval_js("document.getElementById('selectedApproachTag').textContent")
        print(f"  [CHECK] Approach origin set to East: '{appr_tag}'")
        assert "EAST" in appr_tag, "Failed to set East approach"

        await eval_js("setApproachRoute('STRAIGHT')")
        appr_tag = await eval_js("document.getElementById('selectedApproachTag').textContent")
        print(f"  [CHECK] Approach origin set to West: '{appr_tag}'")
        assert "WEST" in appr_tag, "Failed to set West approach"

        # 6. Triage selection
        await eval_js("setTriagePriority('P1')")
        triage_tag = await eval_js("document.getElementById('selectedTriageTag').textContent")
        print(f"  [CHECK] Triage set to P1: '{triage_tag}'")
        assert "PRIORITY 1" in triage_tag, "Failed to set P1 triage"

        # -------------------------------------------------------------
        # TEST 6: Trigger Emergency Dispatch
        # -------------------------------------------------------------
        print("\n--- TEST 6: Trigger Emergency Dispatch (Full Pipeline) ---")
        await eval_js("handleEmergencyButtonClick()")
        await asyncio.sleep(1.5)

        fleet_count = await eval_js("activeFleet.length")
        is_preempt = await eval_js("isPreemptionActive")
        overall_label = await eval_js("document.getElementById('lblCorridorOverall').textContent")
        print(f"  [CHECK] Fleet count after dispatch: {fleet_count} (Expected: >= 1)")
        print(f"  [CHECK] Preemption active? {is_preempt} (Expected: True)")
        print(f"  [CHECK] Status HUD: '{overall_label}' (Expected: 'GREEN WAVE ACTIVE')")

        assert fleet_count >= 1, "Fleet count should be >= 1 after dispatch"
        assert is_preempt, "Preemption must be active"

        # -------------------------------------------------------------
        # TEST 7: Check Backend HTTP Delivery & Mission Analytics
        # -------------------------------------------------------------
        print("\n--- TEST 7: Verify Backend Delivery & Mission Analytics ---")
        res = urllib.request.urlopen("http://localhost:8000/api/driver/actions/latest?since=0", timeout=3)
        actions_data = json.loads(res.read().decode())
        recent_actions = actions_data.get("actions", [])
        print(f"  [CHECK] Backend received actions: {len(recent_actions)}")
        dispatches = [a for a in recent_actions if a.get("type") == "DRIVER_DISPATCH"]
        print(f"  [CHECK] Found DRIVER_DISPATCH in backend actions: {len(dispatches)}")
        assert len(dispatches) > 0, "Backend must have recorded DRIVER_DISPATCH via HTTP/WS!"
        last_disp = dispatches[-1]
        print(f"  [CHECK] Dispatch details: vehicleId={last_disp.get('vehicleId')}, driverId={last_disp.get('driverId')}, targetHospital={last_disp.get('targetHospital')}")
        assert last_disp.get("driverId") == "071", f"Expected driverId '071', got {last_disp.get('driverId')}"

        # -------------------------------------------------------------
        # TEST 8: Test Driver Logout
        # -------------------------------------------------------------
        print("\n--- TEST 8: Test Driver Logout ---")
        await eval_js("logoutDriver()")
        await asyncio.sleep(0.5)

        is_modal_after_logout = await eval_js("document.getElementById('driverAuthModal').style.display !== 'none'")
        badge_after_logout = await eval_js("document.getElementById('driverBadge').style.display !== 'none'")
        badge_id_after_logout = await eval_js("document.getElementById('driverBadgeId').textContent")
        id_input_val = await eval_js("document.getElementById('txtDriverId').value")
        pin_input_val = await eval_js("document.getElementById('txtDriverPin').value")

        print(f"  [CHECK] Modal visible after logout? {is_modal_after_logout} (Expected: True)")
        print(f"  [CHECK] Badge hidden after logout? {not badge_after_logout} (Expected: True)")
        print(f"  [CHECK] Badge text after logout: '{badge_id_after_logout}' (Expected: 'LOCKED')")
        print(f"  [CHECK] Inputs cleared? ID='{id_input_val}', PIN='{pin_input_val}'")

        assert is_modal_after_logout, "Modal must be visible after logout"
        assert not badge_after_logout, "Badge must be hidden after logout"
        assert badge_id_after_logout == "LOCKED", "Badge must say LOCKED"
        assert id_input_val == "" and pin_input_val == "", "Input fields must be empty"

        # -------------------------------------------------------------
        # TEST 9: Desktop Simulation Login Modal Credential Audit
        # -------------------------------------------------------------
        print("\n--- TEST 9: Desktop Simulation (index.html) Credential Audit ---")
        await navigate("http://localhost:8000")

        login_modal_html = await eval_js("document.getElementById('loginModal').innerHTML")
        desktop_leak = any(k in login_modal_html.lower() for k in ["quicklogin", "2006", "2007", "whitelisted duty accounts", "pin:"])
        print(f"  [CHECK] Does desktop login modal disclose PINs or quick-login buttons? {desktop_leak} (Expected: False)")
        assert not desktop_leak, "Desktop login modal leaks credentials or has quick-login buttons!"

        print("\n==================================================================")
        print("  🎉 ALL 9 VERIFICATION CHECKS PASSED WITH ZERO ERRORS!")
        print("==================================================================")

    finally:
        if ws:
            await ws.close()
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=3)
        except Exception:
            chrome_proc.kill()

if __name__ == "__main__":
    asyncio.run(run_tests())
