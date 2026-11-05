import os
import re

scratch_path = r'C:\Users\Bv\.gemini\antigravity\scratch\green_corridor_system\frontend\driver_app.html'
onedrive_path = r'C:\Users\Bv\OneDrive\Documents\green_corridor_system\frontend\driver_app.html'

with open(scratch_path, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. FIX safeSession and safeLocal (replace window.safeSession with window.sessionStorage)
new_safe_storage = '''// Safe Storage Fallback Proxy (Reliable Local & Session Storage)
const _memSession = {};
const _memLocal = {};
const safeSession = {
  getItem: (k) => { try { return window.sessionStorage ? window.sessionStorage.getItem(k) : (_memSession[k] || null); } catch(e) { return _memSession[k] || null; } },
  setItem: (k, v) => { try { _memSession[k] = v; if (window.sessionStorage) window.sessionStorage.setItem(k, v); } catch(e) {} },
  removeItem: (k) => { try { delete _memSession[k]; if (window.sessionStorage) window.sessionStorage.removeItem(k); } catch(e) {} }
};
const safeLocal = {
  getItem: (k) => { try { return window.localStorage ? window.localStorage.getItem(k) : (_memLocal[k] || null); } catch(e) { return _memLocal[k] || null; } },
  setItem: (k, v) => { try { _memLocal[k] = v; if (window.localStorage) window.localStorage.setItem(k, v); } catch(e) {} },
  removeItem: (k) => { try { delete _memLocal[k]; if (window.localStorage) window.localStorage.removeItem(k); } catch(e) {} }
};'''

old_storage_re = re.compile(r'// Safe Storage Fallback Proxy.*?const safeLocal = \{[^}]+\};', re.DOTALL)
text = old_storage_re.sub(new_safe_storage, text)

# 2. Make show/dismiss driverAuthModal rock solid
modal_funcs = '''function showDriverLoginModal() {
  const modal = document.getElementById('driverAuthModal');
  if (modal) modal.style.setProperty('display', 'flex', 'important');
}

function dismissDriverAuthModal() {
  const modal = document.getElementById('driverAuthModal');
  if (modal) modal.style.setProperty('display', 'none', 'important');
}'''

old_modal_re = re.compile(r'function showDriverLoginModal\(\)\s*\{.*?function dismissDriverAuthModal\(\)\s*\{.*?\}', re.DOTALL)
text = old_modal_re.sub(modal_funcs, text)

# 3. Fix checkDriverAuth & loginSuccess to use safeSession and safeLocal
new_login_funcs = '''function loginSuccess(authRecord) {
  inMemoryDriverUser = authRecord;
  try {
    const serialized = JSON.stringify(authRecord);
    safeSession.setItem('GREEN_CORRIDOR_DRIVER_USER', serialized);
    safeLocal.setItem('GREEN_CORRIDOR_DRIVER_USER', serialized);
  } catch(e) {}

  dismissDriverAuthModal();

  const sub = document.getElementById('appHeaderSub');
  if (sub) sub.textContent = `DUTY #${authRecord.id} • 108 AROGYA KAVACHA`;

  reportPresence(true);
  showToast(`✅ Access Granted: ${authRecord.label || ('Driver #' + authRecord.id)}`);
}

function checkDriverAuth() {
  let user = null;
  try {
    user = safeSession.getItem('GREEN_CORRIDOR_DRIVER_USER') || safeLocal.getItem('GREEN_CORRIDOR_DRIVER_USER') || inMemoryDriverUser;
  } catch(e) {}

  if (user) {
    try {
      const uData = (typeof user === 'string') ? JSON.parse(user) : user;
      if (uData && uData.id && AUTHORIZED_DRIVER_ACCOUNTS.some(a => isSameDriverId(a.id, uData.id) || (a.name && a.name.toLowerCase() === String(uData.name || uData.id).toLowerCase()))) {
        inMemoryDriverUser = uData;
        dismissDriverAuthModal();
        const sub = document.getElementById('appHeaderSub');
        if (sub) sub.textContent = `DUTY #${uData.id} • 108 AROGYA KAVACHA`;
        reportPresence(true);
        return;
      }
    } catch(e) {}
  }

  inMemoryDriverUser = null;
  showDriverLoginModal();
}'''

old_login_re = re.compile(r'function loginSuccess\(authRecord\)\s*\{.*?function checkDriverAuth\(\)\s*\{.*?^\}', re.DOTALL | re.MULTILINE)
text = old_login_re.sub(new_login_funcs, text)

# 4. Make button in modal type="button" so it never causes page reload
text = text.replace('<button type="submit" id="btnSubmitDriverAuth" class="btn-auth-submit">',
                    '<button type="button" id="btnSubmitDriverAuth" onclick="handleDriverAuthSubmit(event)" class="btn-auth-submit">')

# 5. Fix form tag to prevent default submit
text = text.replace('<form onsubmit="handleDriverAuthSubmit(event)">',
                    '<form onsubmit="handleDriverAuthSubmit(event); return false;">')

with open(scratch_path, 'w', encoding='utf-8') as f:
    f.write(text)

with open(onedrive_path, 'w', encoding='utf-8') as f:
    f.write(text)

print('SUCCESS: Fixed safeSession and login loop in both driver_app.html copies!')
