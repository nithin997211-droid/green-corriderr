import os
import re

scratch_path = r'C:\Users\Bv\.gemini\antigravity\scratch\green_corridor_system\frontend\driver_app.html'
onedrive_path = r'C:\Users\Bv\OneDrive\Documents\green_corridor_system\frontend\driver_app.html'

with open(scratch_path, 'r', encoding='utf-8') as f:
    text = f.read()

# -------------------------------------------------------------
# FIX 5: Remove Bay 01, Bay 02, Bay 03 words
# -------------------------------------------------------------
text = text.replace('Trauma Bay 01', 'Emergency Trauma Care')
text = text.replace('Bay 02 (J2 South)', 'Palace Road Wing')
text = text.replace('Bay 03 (J1 North)', 'Sayyaji Rao Wing')
text = text.replace('KR Hospital Trauma Bay 01', 'KR Hospital Emergency Trauma Care')
text = text.replace('Apollo Bay 02', 'Apollo BGS Multi-Speciality')
text = text.replace('Manipal Bay 03', 'Manipal Super Speciality')
text = text.replace('BAY 01', 'EMERGENCY TRAUMA')
text = text.replace('BAY 02', 'CARDIAC ICU')
text = text.replace('BAY 03', 'SURGICAL TRAUMA')
text = text.replace('Bay 01 (East)', 'Emergency Trauma Care')
text = text.replace('Bay 02 (South J2)', 'Palace Road Wing')
text = text.replace('Bay 03 (North J1)', 'Sayyaji Rao Wing')

# -------------------------------------------------------------
# FIX 1, 2, 3: Add handleMissionArrival function and call it on arrival
# -------------------------------------------------------------
arrival_func = '''
function handleMissionArrival(hospName) {
  isPreemptionActive = false;
  myActiveVehicleId = null;
  stopSirenTone();

  const overallEl = document.getElementById('lblCorridorOverall');
  if (overallEl) {
    overallEl.textContent = 'SAFELY DOCKED';
    overallEl.style.color = 'var(--emerald)';
  }

  const teleEtaEl = document.getElementById('teleEta');
  if (teleEtaEl) teleEtaEl.textContent = 'ETA 00:00';

  const teleSpeedEl = document.getElementById('teleSpeed');
  if (teleSpeedEl) teleSpeedEl.textContent = '0 km/h (Docked)';

  const glosaSpeedEl = document.getElementById('glosaTargetSpeed');
  if (glosaSpeedEl) glosaSpeedEl.textContent = '0';

  const glosaStatus = document.getElementById('glosaWaveStatus');
  if (glosaStatus) {
    glosaStatus.textContent = 'MISSION COMPLETED';
    glosaStatus.className = 'glosa-badge standby';
  }

  // Turn Trigger Button back to Green Ready State
  const btn = document.getElementById('btnEmergencyTrigger');
  if (btn) {
    btn.classList.remove('active-run');
    btn.style.background = 'var(--emerald)';
  }
  const btnIco = document.getElementById('triggerBtnIcon');
  if (btnIco) btnIco.textContent = '⚡';
  const btnTxt = document.getElementById('triggerBtnText');
  if (btnTxt) btnTxt.textContent = 'TRIGGER GREEN WAVE CORRIDOR';
  const btnSub = document.getElementById('triggerBtnSub');
  if (btnSub) btnSub.textContent = 'READY FOR NEXT EMERGENCY DISPATCH';

  // Mark all 3 cascading junction steps as CLEARED
  for (let i = 1; i <= 3; i++) {
    const item = document.getElementById(`jStep${i}`);
    if (item) item.className = 'junction-row cleared';
    const badge = document.getElementById(`jSigBadge${i}`);
    if (badge) {
      badge.className = 'signal-pill sig-green';
      badge.textContent = 'CLEARED';
    }
    const sub = document.getElementById(`jSub${i}`);
    if (sub) {
      const jNames = ['Ayurvedic Circle', 'Irwin Road Cross', 'KR Hospital Gate'];
      sub.textContent = `${jNames[i-1]} • CLEARED`;
    }
  }

  // Clear active emergency run from activeFleet
  activeFleet = [];
  renderFleetDeck();
  const fleetSec = document.getElementById('fleetSection');
  if (fleetSec) fleetSec.style.display = 'none';

  const hText = hospName || selectedHospitalName || 'Hospital Trauma Center';
  speakGuidance(`Mission accomplished. Safely arrived at ${hText}. Patient handover initiated.`, true);
  showToast(`🎉 Destination Reached! Patient handover at ${hText}.`);
}
'''

if 'function handleMissionArrival' not in text:
    text = text.replace('function handleDriverAuthSubmit', arrival_func + '\nfunction handleDriverAuthSubmit')

# In CORRIDOR_TELEMETRY: when myUnit.arrived || myUnit.cleared, call handleMissionArrival
pattern_arrived = re.compile(r'if\s*\(\s*myUnit\.arrived\s*\|\|\s*myUnit\.cleared\s*\)\s*\{[^}]+\}', re.DOTALL)
text = pattern_arrived.sub('''if (myUnit.arrived || myUnit.cleared) {
        handleMissionArrival(myUnit.hospital);
      }''', text)

# In SIM_ARRIVED: call handleMissionArrival
pattern_sim_arr = re.compile(r'if\s*\(msg\.type\s*===\s*[\'"]SIM_ARRIVED[\'"]\)\s*\{[^}]+\}', re.DOTALL)
text = pattern_sim_arr.sub('''if (msg.type === 'SIM_ARRIVED') {
    handleMissionArrival(msg.hospital);
  }''', text)

# In SIM_CLEARED: call handleMissionArrival
pattern_sim_clr = re.compile(r'else\s*if\s*\(msg\.type\s*===\s*[\'"]SIM_CLEARED[\'"]\)\s*\{[^}]+\}', re.DOTALL)
text = pattern_sim_clr.sub('''else if (msg.type === 'SIM_CLEARED') {
    handleMissionArrival(msg.hospital);
  }''', text)

# -------------------------------------------------------------
# FIX 2: Ensure cascading signal progression works reliably
# -------------------------------------------------------------
j_update_block = '''      const leadU = myUnit || (msg.activeUnits && msg.activeUnits.length > 0 ? msg.activeUnits[0] : null);
      const j1d = leadU ? leadU.j1Dist : (msg.j1 ? msg.j1.dist : 240);
      const j2d = leadU ? leadU.j2Dist : (msg.j2 ? msg.j2.dist : 560);
      const j3d = leadU ? leadU.j3Dist : (msg.j3 ? msg.j3.dist : 890);

      updateJunctionStep(1, {
        name: 'Ayurveda Circle',
        dist: j1d,
        passed: j1d <= -15 || (msg.j1 && msg.j1.passed),
        isPreemptGreen: msg.j1 ? msg.j1.isPreemptGreen : true,
        isPreemptClearance: msg.j1 ? msg.j1.isPreemptClearance : false,
        signalColor: msg.j1 ? msg.j1.signalColor : 'GREEN'
      });

      updateJunctionStep(2, {
        name: 'Irwin Road Cross',
        dist: j2d,
        passed: j2d <= -15 || (msg.j2 && msg.j2.passed),
        isPreemptGreen: msg.j2 ? msg.j2.isPreemptGreen : true,
        isPreemptClearance: msg.j2 ? msg.j2.isPreemptClearance : false,
        signalColor: msg.j2 ? msg.j2.signalColor : 'GREEN'
      });

      updateJunctionStep(3, {
        name: 'KR Hospital Gate',
        dist: j3d,
        passed: j3d <= -15 || (msg.j3 && msg.j3.passed),
        isPreemptGreen: msg.j3 ? msg.j3.isPreemptGreen : true,
        isPreemptClearance: msg.j3 ? msg.j3.isPreemptClearance : false,
        signalColor: msg.j3 ? msg.j3.signalColor : 'GREEN'
      });'''

old_j_pattern = re.compile(r'updateJunctionStep\(1,\s*\{.*?\}\);\s*updateJunctionStep\(2,\s*\{.*?\}\);\s*updateJunctionStep\(3,\s*\{.*?\}\);', re.DOTALL)
text = old_j_pattern.sub(j_update_block, text)

# -------------------------------------------------------------
# FIX 4: Truly Dynamic GLOSA & Voice Guidance
# -------------------------------------------------------------
new_glosa_func = '''function updateGlosaDeck(myUnit, msg) {
  const speedEl = document.getElementById('glosaTargetSpeed');
  const juncEl = document.getElementById('glosaTargetJunc');
  const distEl = document.getElementById('glosaDistToJunc');
  const barEl = document.getElementById('glosaSpeedBar');
  const statusEl = document.getElementById('glosaWaveStatus');

  if (!myUnit || myUnit.arrived || myUnit.cleared) {
    if (speedEl) speedEl.textContent = '0';
    if (juncEl) juncEl.textContent = 'STANDBY';
    if (distEl) distEl.textContent = '-- m';
    if (statusEl) {
      statusEl.textContent = 'STANDBY';
      statusEl.className = 'glosa-badge standby';
    }
    return;
  }

  let targetJuncName = 'J1 • Ayurvedic Circle';
  let targetDist = myUnit.j1Dist;

  if (myUnit.j1Dist <= -15) {
    if (myUnit.j2Dist > -15) {
      targetJuncName = 'J2 • Irwin Rd Cross';
      targetDist = myUnit.j2Dist;
    } else {
      targetJuncName = 'J3 • KR Gate';
      targetDist = myUnit.j3Dist;
    }
  }

  // Dynamic GLOSA speed calculation
  let optimalSpeed = 65;
  let waveBadgeText = '⚡ ZERO-STOP WAVE';

  if (targetDist > 300) {
    optimalSpeed = 70;
    waveBadgeText = '⚡ CORRIDOR ACCELERATE';
  } else if (targetDist > 140) {
    optimalSpeed = 62;
    waveBadgeText = '🟢 GREEN WAVE CRUISE';
  } else if (targetDist > 40) {
    optimalSpeed = 52;
    waveBadgeText = '⚡ QUEUE FLUSH GLIDE';
  } else if (targetDist > -15) {
    optimalSpeed = 45;
    waveBadgeText = '🟡 CROSSING STOP-BAR';
  } else {
    optimalSpeed = 65;
    waveBadgeText = '🟢 ADVANCING TO NEXT';
  }

  if (myUnit.j3Dist !== undefined && myUnit.j3Dist <= 60 && myUnit.j3Dist > -10) {
    optimalSpeed = 25;
    waveBadgeText = '🏥 HOSPITAL SLOW-DOWN';
  }

  if (speedEl) speedEl.textContent = Math.round(optimalSpeed);
  if (juncEl) juncEl.textContent = targetJuncName + ' • GREEN LOCK';
  if (distEl) distEl.textContent = (targetDist > -15) ? `${Math.max(0, Math.round(targetDist))} m` : 'CLEARED';
  if (barEl) {
    const barPct = Math.min(100, Math.max(10, ((optimalSpeed - 20) / (80 - 20)) * 100));
    barEl.style.width = `${barPct}%`;
  }
  if (statusEl) {
    statusEl.textContent = waveBadgeText;
    statusEl.className = 'glosa-badge';
  }
}'''

old_glosa_pattern = re.compile(r'function updateGlosaDeck\(myUnit,\s*msg\)\s*\{.*?^\}', re.DOTALL | re.MULTILINE)
text = old_glosa_pattern.sub(new_glosa_func, text)

# Dynamic updateVoiceGuidance
new_voice_func = '''function updateVoiceGuidance(myUnit, msg) {
  if (!myUnit || myUnit.arrived || myUnit.cleared) return;
  const runId = myUnit.id || 'EV';
  if (!myVoiceMilestones[runId]) {
    myVoiceMilestones[runId] = {
      started: false,
      j1Appr: false,
      j1Clear: false,
      j2Appr: false,
      j2Clear: false,
      j3Appr: false,
      j3Clear: false,
      hospEntry: false
    };
  }
  const m = myVoiceMilestones[runId];

  if (!m.started) {
    m.started = true;
    const vName = (currentVehicleType === 'FIRE_BRIGADE') ? 'Fire Tender' : (currentVehicleType === 'POLICE' ? 'Police Unit' : '108 Ambulance');
    speakGuidance(`Emergency green wave engaged for ${vName}. Clear corridor towards ${selectedHospitalName}. Accelerate to 65.`);
    return;
  }

  if (myUnit.j1Dist < 200 && myUnit.j1Dist > 80 && !m.j1Appr) {
    m.j1Appr = true;
    speakGuidance("Approaching Ayurvedic Circle. Signal locked green, glide at 55.");
  }
  if (myUnit.j1Dist <= -15 && !m.j1Clear) {
    m.j1Clear = true;
    speakGuidance("Ayurvedic Circle cleared. Advance towards Irwin Crossing.");
  }
  if (myUnit.j2Dist < 220 && myUnit.j2Dist > 80 && !m.j2Appr) {
    m.j2Appr = true;
    speakGuidance("Irwin Road Crossing green wave active. Queue cleared.");
  }
  if (myUnit.j2Dist <= -15 && !m.j2Clear) {
    m.j2Clear = true;
    speakGuidance("Junction 2 cleared. Final stretch to hospital gate.");
  }
  if (myUnit.j3Dist < 180 && myUnit.j3Dist > 60 && !m.j3Appr) {
    m.j3Appr = true;
    speakGuidance("Approaching KR Hospital Gate. Preemption green confirmed.");
  }
  if (myUnit.j3Dist <= 50 && !m.hospEntry) {
    m.hospEntry = true;
    speakGuidance("Entering casualty apron. Decelerate to 25 for handover.");
  }
}'''

old_voice_pattern = re.compile(r'function updateVoiceGuidance\(myUnit,\s*msg\)\s*\{.*?^\}', re.DOTALL | re.MULTILINE)
text = old_voice_pattern.sub(new_voice_func, text)

# Write to scratch
with open(scratch_path, 'w', encoding='utf-8') as f:
    f.write(text)

# Write to onedrive
with open(onedrive_path, 'w', encoding='utf-8') as f:
    f.write(text)

print('SUCCESS: Both files updated cleanly!')
