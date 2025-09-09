# services/polygon_service.py
"""
Polygon.io EOD service (drop-in, OI fixed)
- EOD Open Interest via /v3/snapshot/options/{underlying}?expiration_date=...
  (open_interest = quantity held at end of last trading day)
- Prior-day price & volume via /v2/aggs/ticker/O:.../prev
- Back-compatible API used by your routes:
    get_market_phase, get_stock_quote, get_options_expirations, get_options_chain
"""
from __future__ import annotations

import os
import time
import math
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

POLY_KEY = os.getenv("POLYGON_API_KEY") or os.getenv("POLY_API_KEY")
BASE_V2 = "https://api.polygon.io/v2"
BASE_V3 = "https://api.polygon.io/v3"

_http = requests.Session()
_http.headers.update({"Accept-Encoding": "gzip"})

# ---- Throttle / Limits (tune via env) ----
MAX_RPS = float(os.getenv("POLY_MAX_RPS", "4.5"))
DELAY = 1.0 / MAX_RPS if MAX_RPS > 0 else 0.25
MAX_WORKERS = int(os.getenv("POLY_MAX_WORKERS", "6"))

def _get(url: str, params: dict | None = None, timeout: int = 30) -> dict:
    if not POLY_KEY:
        raise RuntimeError("Missing POLYGON_API_KEY")
    q = dict(params or {})
    q["apiKey"] = POLY_KEY
    if DELAY:
        time.sleep(DELAY)
    r = _http.get(url, params=q, timeout=timeout)
    r.raise_for_status()
    return r.json() or {}

def _ms_to_date(ms: int | float | None) -> Optional[str]:
    if ms is None:
        return None
    try:
        return datetime.utcfromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d")
    except Exception:
        return None

def _last_session_date_from_prev_stock(symbol: str) -> str:
    """Use stock /prev bar to get authoritative last trading date."""
    try:
        j = _get(f"{BASE_V2}/aggs/ticker/{symbol}/prev", {"adjusted": "true"})
        res = j.get("results") or []
        if res:
            d = _ms_to_date(res[0].get("t") or res[0].get("T"))
            if d:
                return d
    except Exception:
        pass
    # fallback: last weekday (UTC)
    d = datetime.utcnow().date()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")

# ---------------- Quotes ----------------
def _quote_prev_close(symbol: str) -> Tuple[Optional[float], str]:
    try:
        j = _get(f"{BASE_V2}/aggs/ticker/{symbol}/prev", {"adjusted": "true"})
        res = j.get("results") or []
        if res:
            return float(res[0]["c"]), "stocks-prev"
    except Exception as e:
        print(f"[quote_prev_close] {symbol} error: {e}")
    return None, "unavailable"

def get_stock_quote(symbol: str) -> Dict:
    px, src = _quote_prev_close(symbol)
    if px is None:
        return {"symbol": symbol, "error": "No price", "source": src}
    return {"symbol": symbol, "price": round(float(px), 4), "source": src}

# -------------- Expirations --------------
def get_options_expirations(symbol: str) -> List[str]:
    """Expirations via reference/contracts as_of last session."""
    as_of = _last_session_date_from_prev_stock(symbol)
    url = f"{BASE_V3}/reference/options/contracts"
    params = {
        "underlying_ticker": symbol,
        "as_of": as_of,
        "limit": 1000,
        "sort": "expiration_date",
        "order": "asc",
    }
    out, seen, next_url = [], set(), None
    try:
        while True:
            j = _get(next_url or url, params if not next_url else {})
            for row in j.get("results") or []:
                exp = (row.get("expiration_date") or "")[:10]
                if exp and exp not in seen:
                    seen.add(exp)
                    out.append(exp)
            next_url = j.get("next_url")
            if not next_url:
                break
    except Exception as e:
        print(f"[expirations] {symbol} error: {e}")
    out.sort()
    return out[:40]

# -------------- Helpers --------------
def _prev_bar_option(ticker: str) -> Tuple[Optional[float], int]:
    """(lastPrice, volume) from prior session for an option contract."""
    try:
        j = _get(f"{BASE_V2}/aggs/ticker/{ticker}/prev", {"adjusted": "true"})
        res = j.get("results") or []
        if not res:
            return None, 0
        row = res[0]
        close_px = row.get("c")
        vol = row.get("v") or 0
        return (float(close_px) if close_px is not None else None, int(vol))
    except Exception as e:
        print(f"[prev-bar] {ticker} error: {e}")
        return None, 0

def _from_snapshot_day(day: dict | None) -> Tuple[Optional[float], int]:
    """Map snapshot 'day' object to (close, volume) if present."""
    if not isinstance(day, dict):
        return None, 0
    close_px = day.get("c")
    vol = day.get("v") or 0
    return (float(close_px) if close_px is not None else None, int(vol))

# -------------- Chain (EOD) --------------
def get_options_chain(symbol: str, expiration_date: str) -> Dict:
    """
    Build an options chain for the requested expiration using:
      - open_interest from /v3/snapshot/options/{underlying}?expiration_date=...
        (EOD OI for last trading day)
      - price/volume from snapshot 'day' when available;
        else fallback to /v2/aggs/ticker/O:.../prev
    """
    # 1) Fetch snapshot pages filtered to the expiration
    url = f"{BASE_V3}/snapshot/options/{symbol}"
    params = {
        "expiration_date": expiration_date,
        "limit": 250,
        "sort": "strike_price",
        "order": "asc",
    }
    pages = []
    next_url = None
    try:
        while True:
            j = _get(next_url or url, params if not next_url else {})
            pages.extend(j.get("results") or [])
            next_url = j.get("next_url")
            if not next_url:
                break
    except Exception as e:
        print(f"[snapshot-chain] {symbol} {expiration_date} error: {e}")

    calls: List[dict] = []
    puts: List[dict] = []

    def normalize(item: dict) -> Optional[dict]:
        try:
            details = item.get("details") or {}
            # polygon returns open_interest as a top-level field in snapshot items
            oi = int(item.get("open_interest") or 0)

            # prefer snapshot day bar for prior-day values; fallback to /prev
            last_px, vol = _from_snapshot_day(item.get("day"))
            ticker = details.get("ticker") or details.get("option_symbol") or details.get("symbol") \
                     or item.get("ticker") or item.get("option_symbol")

            if (last_px is None or vol == 0) and ticker:
                px2, vol2 = _prev_bar_option(ticker)
                # choose whichever gives us a price; prefer snapshot if present
                last = last_px if last_px is not None else px2
                volume = vol if vol else vol2
            else:
                last = last_px
                volume = vol

            return {
                "ticker": ticker,
                "strike": float(details.get("strike_price")),
                "lastPrice": float(last) if last is not None else 0.0,
                "volume": int(volume or 0),
                "openInterest": oi,
                "contractType": (details.get("contract_type") or "").lower(),
            }
        except Exception as e:
            print(f"[normalize] error: {e}")
            return None

    # 2) Normalize in a small pool
    if pages:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = [ex.submit(normalize, it) for it in pages]
            for f in as_completed(futs):
                row = f.result()
                if not row:
                    continue
                if row["contractType"] == "call":
                    calls.append({k: v for k, v in row.items() if k != "contractType"})
                else:
                    puts.append({k: v for k, v in row.items() if k != "contractType"})

    # 3) Spot for reference/metadata
    spot, _ = _quote_prev_close(symbol)
    as_of = _last_session_date_from_prev_stock(symbol)

    return {
        "symbol": symbol,
        "date": expiration_date,
        "calls": calls,
        "puts": puts,
        "metadata": {
            "dataSource": "polygon-snapshot+prev",
            "asOf": as_of,
            "spot": round(float(spot), 4) if spot else None,
            "contractsReturned": len(pages),
        },
    }

# ---------------- Phase label ----------------
def get_market_phase(ttl: int = 15) -> str:
    try:
        now = datetime.utcnow()
        ny = now - timedelta(hours=4)  # naive ET offset
        if ny.weekday() >= 5:
            return "closed"
        m = ny.hour * 60 + ny.minute
        if 9*60+30 <= m <= 16*60:
            return "open"
        return "pre" if m < 9*60+30 else "afterhours"
    except Exception:
        return "unknown"
