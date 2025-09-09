# services/market_clock.py
import os, time, requests
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

POLY_KEY = os.getenv("POLYGON_API_KEY")
_session = requests.Session()
_session.headers["Accept-Encoding"] = "gzip"

_cache = {"ts": 0.0, "data": None}

def _status_polygon(timeout=2.5):
    if not POLY_KEY:
        return None
    try:
        r = _session.get(
            "https://api.polygon.io/v1/marketstatus/now",
            params={"apiKey": POLY_KEY},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json() or {}
        return {
            "is_open": (str(data.get("market", "")).lower() == "open"),
            "source": "polygon",
            "raw": data,
        }
    except Exception:
        return None

def _status_clock():
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    start, end = dtime(9, 30), dtime(16, 0)
    is_open = (now.weekday() < 5) and (start <= now.time() <= end)
    return {
        "is_open": bool(is_open),
        "source": "clock-fallback",
        "raw": {"weekday": now.weekday(), "time_et": now.time().isoformat(timespec="minutes")},
    }

def get_market_status(ttl_seconds: int = 15):
    now = time.time()
    if _cache["data"] and (now - _cache["ts"] < ttl_seconds):
        return _cache["data"]
    s = _status_polygon() or _status_clock()
    _cache.update(ts=now, data=s)
    return s

def market_mode() -> str:
    return "live" if get_market_status().get("is_open") else "eod"

def is_regular_session_open() -> bool:
    return market_mode() == "live"
