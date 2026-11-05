import os
from typing import Optional
from supabase import create_client, Client

# Load environment variables from .env file if present
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _k = _k.strip()
                    _v = _v.strip().strip("'\"")
                    if _k:
                        os.environ[_k] = _v
    except Exception:
        pass

_raw_url = os.getenv("SUPABASE_URL", "https://rawzqusqyewjioxolsxi.supabase.co").strip()
if _raw_url and not _raw_url.startswith("http"):
    if ".supabase.co" not in _raw_url:
        _raw_url = f"https://{_raw_url}.supabase.co"
    else:
        _raw_url = f"https://{_raw_url}"

SUPABASE_URL = _raw_url
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_oYpHZrI5VtUiFkHi6TBWNg_wSW1d_vE").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", SUPABASE_KEY).strip()

supabase: Optional[Client] = None

try:
    if SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL.startswith("http"):
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    # Safe fallback if credentials or network is unavailable
    print(f"[INFO] Supabase Client initialization note: {e}")
    supabase = None

def get_supabase_client() -> Optional[Client]:
    return supabase

def is_supabase_enabled() -> bool:
    return supabase is not None and "xyzcompany" not in SUPABASE_URL
