# services/polygon_service.py
"""Polygon.io EOD service — drop-in replacement for services/polygon_service.py

Fixes:
- Zero volume/OI by using true end-of-day (EOD) sources
- Avoids snapshot mixing
- Paginates contracts with `as_of` date for stable OI
- Throttles per-contract EOD bar calls
"""
from __future__ import annotations

import os
import time
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import requests
from datetime import datetime, timedelta, timezone

# --- Config ---
POLY_KEY = os.getenv("POLYGON_API_KEY") or os.getenv("POLY_API_KEY")
HTTP = requests.Session()
HTTP.headers.update({"Accept-Encoding": "gzip"})
BASE_V2 = "https://api.polygon.io/v2"
BASE_V3 = "https://api.polygon.io/v3"

# Simple rate throttle (best-effort; also keep worker count small)
MAX_RPS = float(os.getenv("POLY_MAX_RPS", "4.5"))
SLEEP_BETWEEN_CALLS = 1.0 / MAX_RPS if MAX_RPS > 0 else 0.25
MAX_WORKERS = int(os.getenv("POLY_MAX_WORKERS", "5"))
MAX_CONTRACTS = int(os.getenv("POLY_MAX_CONTRACTS", "400"))  # cap per chain to avoid rate limits

# --- Helpers ---

def _get(url: str, params: dict | None = None, timeout: int = 20) -> dict:
    if not POLY_KEY:
        raise RuntimeError("Missing POLYGON_API_KEY")
    p = dict(params or {})
    p["apiKey"] = POLY_KEY
    if SLEEP_BETWEEN_CALLS:
        time.sleep(SLEEP_BETWEEN_CALLS)  # soft throttle
    r = HTTP.get(url, params=p, timeout=timeout)
    r.raise_for_status()
    return r.json()

def get_market_phase(ttl: int = 15) -> str:
    """Cheap, dependency-free phase label for UI only."""
    try:
        now = datetime.utcnow()
        ny = now - timedelta(hours=4)  # approximate ET
        if ny.weekday() >= 5:
            return "closed"
        minutes = ny.hour * 60 + ny.minute
        if 9*60 + 30 <= minutes <= 16*60:
            return "open"
        elif minutes > 16*60:
            return "afterhours"
        else:
            return "pre"
    except Exception:
        return "unknown"

def _ms_to_date(ms: int) -> str:
    return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d")

def _last_session_date_from_prev_stock(symbol: str) -> str:
    """Use stocks prev bar to get authoritative last trading date."""
    j = _get(f"{BASE_V2}/aggs/ticker/{symbol}/prev", {"adjusted": "true"})
    res = (j or {}).get("results") or []
    if not res:
        d = datetime.utcnow().date()
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d.strftime("%Y-%m-%d")
    return _ms_to_date(res[0].get("t") or res[0].get("T"))

# --- Quotes ---

def quote_delayed(symbol: str, timeout: int = 15) -> Tuple[Optional[float], str]:
    """
    Return a delayed/EOD price for the underlying.
    Primary: previous day close via /v2/aggs/{symbol}/prev (stable on weekends/holidays).
    """
    try:
        j = _get(f"{BASE_V2}/aggs/ticker/{symbol}/prev", {"adjusted": "true"}, timeout=timeout)
        res = (j or {}).get("results") or []
        if res:
            return float(res[0]["c"]), "stocks-prev"
    except Exception as e:
        print(f"[quote_delayed] prev fail for {symbol}: {e}")

    # As a last resort, try snapshot last trade (not EOD-guaranteed)
    try:
        j = _get(f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}", {}, timeout=timeout)
        last = ((j or {}).get("ticker") or {}).get("lastTrade") or {}
        if "p" in last:
            return float(last["p"]), "stocks-snapshot"
    except Exception as e:
        print(f"[quote_delayed] snapshot fail for {symbol}: {e}")
    return None, "unavailable"

def get_stock_quote(symbol: str) -> Dict:
    price, source = quote_delayed(symbol)
    if price is None:
        return {"symbol": symbol, "error": "No price", "source": source}
    return {
        "symbol": symbol,
        "price": round(float(price), 4),
        "source": source,
        "note": "Delayed/EOD price; uses previous session close when market is closed.",
    }

# --- Expirations ---

def get_options_expirations(symbol: str) -> List[str]:
    """
    Build a unique, sorted list of upcoming expiration dates from contracts.
    Pages through /v3/reference/options/contracts.
    """
    as_of = _last_session_date_from_prev_stock(symbol)
    url = f"{BASE_V3}/reference/options/contracts"
    params = {
        "underlying_ticker": symbol,
        "as_of": as_of,
        "limit": 1000,
        "sort": "expiration_date",
        "order": "asc",
    }
    expirations: List[str] = []
    seen = set()
    next_url: Optional[str] = None
    try:
        while True:
            j = _get(next_url or url, params if not next_url else {})
            results = (j or {}).get("results") or []
            for row in results:
                exp = (row.get("expiration_date") or "")[:10]
                if exp and exp >= as_of and exp not in seen:
                    seen.add(exp)
                    expirations.append(exp)
            next_url = (j or {}).get("next_url")
            if not next_url:
                break
    except Exception as e:
        print(f"[expirations] error for {symbol}: {e}")

    expirations.sort()
    return expirations[:40]  # keep the dropdown tidy

# --- Chain (EOD) ---

def _fetch_contracts_for_date(symbol: str, expiration_date: str, as_of: str) -> List[dict]:
    url = f"{BASE_V3}/reference/options/contracts"
    params = {
        "underlying_ticker": symbol,
        "expiration_date": expiration_date,
        "as_of": as_of,
        "limit": 1000,
        "order": "asc",
        "sort": "strike_price",
    }
    results: List[dict] = []
    next_url: Optional[str] = None
    while True:
        j = _get(next_url or url, params if not next_url else {})
        batch = (j or {}).get("results") or []
        results.extend(batch)
        next_url = (j or {}).get("next_url")
        if not next_url:
            break
    return results

def _prev_bar_for_option(ticker: str) -> Tuple[Optional[float], int]:
    """
    Return (lastPriceEOD, volumeEOD) for a given option contract via /v2/aggs/{O:...}/prev.
    If no bar exists for the session, returns (None, 0).
    """
    try:
        j = _get(f"{BASE_V2}/aggs/ticker/{ticker}/prev", {"adjusted": "true"})
        res = (j or {}).get("results") or []
        if not res:
            return None, 0
        row = res[0]
        last_price = float(row.get("c")) if row.get("c") is not None else None
        vol = int(row.get("v") or 0)
        return last_price, vol
    except Exception as e:
        print(f"[prev] error for {ticker}: {e}")
        return None, 0

def _filter_contracts(rows: List[dict], spot: Optional[float]) -> List[dict]:
    """
    Keep a manageable subset for live API mode to avoid rate limits.
    Strategy:
      1) If we know spot, keep strikes within ±15 steps around spot
      2) Always keep top contracts by open_interest up to MAX_CONTRACTS
    """
    if not rows:
        return rows
    # Normalize and collect
    out = []
    for r in rows:
        try:
            ticker = r.get("ticker") or r.get("contract_ticker")
            strike = float(r.get("strike_price"))
            typ = (r.get("contract_type") or "").lower()
            oi = int(r.get("open_interest") or 0)
            out.append({"ticker": ticker, "strike": strike, "type": typ, "oi": oi, "raw": r})
        except Exception:
            continue

    # If we have spot, keep a window of strikes around it
    subset = out
    if spot is not None and not math.isnan(spot):
        strikes = sorted({row["strike"] for row in out})
        if len(strikes) >= 2:
            steps = sorted([round(strikes[i+1] - strikes[i], 2) for i in range(len(strikes)-1)])
            step = steps[len(steps)//2] if steps else 5.0
        else:
            step = 5.0
        low = spot - step * 15
        high = spot + step * 15
        subset = [row for row in out if low <= row["strike"] <= high]

    # Ensure we keep top by OI up to MAX_CONTRACTS
    subset.sort(key=lambda r: r["oi"], reverse=True)
    return subset[:MAX_CONTRACTS]

def get_options_chain(symbol: str, expiration_date: str) -> Dict:
    """
    Return EOD options chain for given symbol and expiration date.

    - OI: from /v3/reference/options/contracts with as_of = last stock session
    - price/volume: from /v2/aggs/{O:…}/prev
    """
    market_phase = get_market_phase()
    as_of = _last_session_date_from_prev_stock(symbol)

    # spot for filtering window & pct calculations client-side
    spot, _ = quote_delayed(symbol)
    try:
        raw_contracts = _fetch_contracts_for_date(symbol, expiration_date, as_of)
    except Exception as e:
        print(f"[chain] contracts fetch failed: {e}")
        raw_contracts = []

    # Filter to avoid per-contract fan-out explosion when calling /prev
    contracts = _filter_contracts(raw_contracts, spot)

    # Fetch prev bars with small parallelism
    calls: List[dict] = []
    puts: List[dict] = []

    def work(row):
        tkr = row["ticker"]
        px, vol = _prev_bar_for_option(tkr)
        oi = int(row["raw"].get("open_interest") or 0)
        strike = float(row["strike"])
        side = row["type"]  # "call" or "put"
        return {
            "type": side,
            "strike": strike,
            "lastPrice": round(float(px), 6) if px is not None else 0.0,
            "volume": int(vol),
            "openInterest": int(oi),
            "ticker": tkr,
        }

    if contracts:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
            futs = [exe.submit(work, row) for row in contracts]
            for fut in as_completed(futs):
                try:
                    item = fut.result()
                    if item["type"] == "call":
                        calls.append({k: v for k, v in item.items() if k != "type"})
                    else:
                        puts.append({k: v for k, v in item.items() if k != "type"})
                except Exception as e:
                    print(f"[chain] worker error: {e}")

    data = {
        "symbol": symbol,
        "date": expiration_date,
        "calls": calls,
        "puts": puts,
        "metadata": {
            "dataSource": "polygon-eod",
            "marketPhase": market_phase,
            "asOf": as_of,
            "contractsReturned": len(contracts),
            "contractsTotal": len(raw_contracts),
            "spot": round(float(spot), 4) if spot else None,
        },
    }
    return data

# --- Back-compat shim (if your app uses this somewhere else) ---

def get_contract_data(symbol: str, expiration_date: str) -> Dict:
    """Alias to get_options_chain for backward compatibility."""
    return get_options_chain(symbol, expiration_date)