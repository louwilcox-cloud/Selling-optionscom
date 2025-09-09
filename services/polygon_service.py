# services/polygon_service.py
import os, requests
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, Tuple, List

from services.market_clock import market_mode, is_regular_session_open

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
if not POLYGON_API_KEY:
    raise RuntimeError("Missing POLYGON_API_KEY in environment.")

_session = requests.Session()
_session.headers["Accept-Encoding"] = "gzip"

# -------------------------- HTTP helpers --------------------------

def _get(url: str, params: Dict[str, Any] | None = None, timeout: float = 6.0) -> Dict[str, Any]:
    p = dict(params or {})
    p["apiKey"] = POLYGON_API_KEY
    r = _session.get(url, params=p, timeout=timeout)
    r.raise_for_status()
    return r.json() or {}

def _get_follow(next_url: str, timeout: float = 10.0) -> Dict[str, Any]:
    # follow polygon's next_url
    if ("apiKey=" not in next_url) and ("?" in next_url):
        next_url = f"{next_url}&apiKey={POLYGON_API_KEY}"
    elif ("apiKey=" not in next_url):
        next_url = f"{next_url}?apiKey={POLYGON_API_KEY}"
    r = _session.get(next_url, timeout=timeout)
    r.raise_for_status()
    return r.json() or {}

def _is_valid(px: Optional[float]) -> bool:
    try:
        return px is not None and float(px) > 0.0
    except Exception:
        return False

# -------------------------- Quotes (stocks) --------------------------

def _prev_close(symbol: str) -> Optional[float]:
    j = _get(f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev", {"adjusted": "true"})
    results = j.get("results") or []
    px = float(results[0]["c"]) if results else None
    return px if _is_valid(px) else None

def _snapshot_live_with_fallbacks(symbol: str) -> Tuple[Optional[float], str]:
    # Stocks snapshot (delayed/real based on plan)
    j = _get(f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
    t = (j.get("ticker") or {})

    # 1) last trade
    lt = (t.get("lastTrade") or {}).get("p")
    if _is_valid(lt):
        return float(lt), "polygon-snapshot:lastTrade"

    # 2) last quote mid
    lq = t.get("lastQuote") or {}
    bp, ap = lq.get("bp"), lq.get("ap")
    if _is_valid(bp) and _is_valid(ap):
        try:
            return (float(bp) + float(ap)) / 2.0, "polygon-snapshot:midQuote"
        except Exception:
            pass

    # 3) today's running close
    day = t.get("day") or {}
    day_c = day.get("c")
    if _is_valid(day_c):
        return float(day_c), "polygon-snapshot:day.c"

    # 4) today's open
    day_o = day.get("o")
    if _is_valid(day_o):
        return float(day_o), "polygon-snapshot:day.o"

    # 5) yesterday close from snapshot payload
    prev = t.get("prevDay") or {}
    prev_c = prev.get("c")
    if _is_valid(prev_c):
        return float(prev_c), "polygon-snapshot:prevDay.c"

    return None, "polygon-snapshot:none"

def get_stock_quote(symbol: str) -> Dict[str, Any]:
    """
    Guaranteed numeric price (>0) with a clear source:
    - If regular session is OPEN: snapshot fallbacks -> prev close
    - Otherwise: prev close -> snapshot fallbacks
    """
    sym = symbol.upper().strip()
    mode = market_mode()
    et = ZoneInfo("America/New_York")
    now_iso = datetime.now(et).isoformat(timespec="seconds")

    last_err = None
    if mode == "live":
        try:
            px, src = _snapshot_live_with_fallbacks(sym)
            if _is_valid(px):
                return {"symbol": sym, "mode": mode, "price": float(px), "source": src, "at": now_iso}
        except Exception as e:
            last_err = e
        px = _prev_close(sym)
        if _is_valid(px):
            return {"symbol": sym, "mode": mode, "price": float(px), "source": "polygon-prev", "at": now_iso}
        raise RuntimeError(f"Quote lookup failed (live) for {sym}: {last_err or 'no valid snapshot and no prev close'}")
    else:
        px = _prev_close(sym)
        if _is_valid(px):
            return {"symbol": sym, "mode": mode, "price": float(px), "source": "polygon-prev", "at": now_iso}
        try:
            px, src = _snapshot_live_with_fallbacks(sym)
            if _is_valid(px):
                return {"symbol": sym, "mode": mode, "price": float(px), "source": src, "at": now_iso}
        except Exception as e:
            last_err = e
        raise RuntimeError(f"Quote lookup failed (eod) for {sym}: {last_err or 'no prev close and no valid snapshot'}")

# --------- Compatibility shims so route imports never crash ---------

def get_market_phase(ttl: int = 15) -> str:
    return "open" if is_regular_session_open() else "closed"

def quote_delayed(symbol: str) -> Tuple[float, str]:
    """Strict EOD (prev close) — kept only for backward compatibility with older code paths."""
    sym = symbol.upper().strip()
    px = _prev_close(sym)
    if not _is_valid(px):
        raise RuntimeError(f"quote_delayed failed for {sym}: no prev close")
    return float(px), "polygon-prev"

# -------------------------- Options: expirations (FIXED: pagination) --------------------------

def get_options_expirations(symbol: str) -> Dict[str, Any]:
    """
    Return unique expiration dates (YYYY-MM-DD) for the underlying, sorted ASC.
    Uses Polygon Options Contracts API. (v3/reference/options/contracts)
    Now paginates through next_url to avoid truncation.
    """
    sym = symbol.upper().strip()
    url = "https://api.polygon.io/v3/reference/options/contracts"
    params = {
        "underlying_ticker": sym,
        "sort": "expiration_date",
        "order": "asc",
        "expired": "false",
        "limit": 1000,
    }

    expirations: set[str] = set()
    pages = 0

    j = _get(url, params)
    while True:
        pages += 1
        results = j.get("results") or []
        for r in results:
            ed = r.get("expiration_date")
            if ed:
                expirations.add(ed)
        next_url = j.get("next_url")
        if not next_url:
            break
        j = _get_follow(next_url)

    exps = sorted(expirations)
    return {"symbol": sym, "expirations": exps, "count": len(exps), "source": "polygon-v3-contracts"}

# -------------------------- Options: chain builders --------------------------

def _prev_contract_bar(contract_ticker: str) -> Tuple[Optional[float], Optional[int]]:
    """Per-contract prev-day aggregate: returns (close, volume) or (None, None)."""
    try:
        q = _get(f"https://api.polygon.io/v2/aggs/ticker/{contract_ticker}/prev", {"adjusted": "true"})
        rs = q.get("results") or []
        if rs:
            c = rs[0].get("c")
            v = rs[0].get("v")
            return (float(c) if _is_valid(c) else None, int(v) if v is not None else None)
    except Exception:
        pass
    return (None, None)

def _chain_via_snapshot(sym: str, expiration: str, fill_zeros: bool) -> Dict[str, Any]:
    """
    Option Chain Snapshot (paged).
    LIVE mapping uses trades only:
      lastPrice <- last_trade.price
      volume    <- day.volume
      OI        <- open_interest
    When fill_zeros=True, backfill lastPrice from prev-day bars for rows where lastPrice == 0.
    """
    base = f"https://api.polygon.io/v3/snapshot/options/{sym}"
    params = {"expiration_date": expiration, "limit": 250, "order": "asc", "sort": "strike_price"}
    out_calls: List[Dict[str, Any]] = []
    out_puts: List[Dict[str, Any]] = []

    page = 0
    j = _get(base, params)
    while True:
        page += 1
        results = j.get("results") or []
        for r in results:
            details = r.get("details") or {}
            ctype = (details.get("contract_type") or "").lower()
            strike = details.get("strike_price")
            ticker = details.get("ticker")

            # ✅ Correct fields for OPTIONS snapshot
            lt = r.get("last_trade") or {}
            last_trade_price = lt.get("price")
            last_price = float(last_trade_price) if _is_valid(last_trade_price) else 0.0

            day = r.get("day") or {}
            vol = day.get("volume")  # intraday running volume
            oi = r.get("open_interest")

            row = {
                "ticker": ticker,
                "strike": float(strike) if strike is not None else None,
                "lastPrice": last_price,
                "volume": int(vol) if isinstance(vol, (int, float)) else 0,
                "openInterest": int(oi) if isinstance(oi, (int, float)) else 0,
            }
            if ctype == "call":
                out_calls.append(row)
            elif ctype == "put":
                out_puts.append(row)

        next_url = j.get("next_url")
        if not next_url:
            break
        j = _get_follow(next_url)

    # Optional EOD-style fill: replace zeros with prev-day close (+ prev volume if available)
    backfilled_calls = backfilled_puts = 0
    if fill_zeros:
        def _backfill(rows: List[Dict[str, Any]], cap: int = 60) -> int:
            fixed = 0
            for row in rows:
                if row["lastPrice"] <= 0.0 and row.get("ticker"):
                    px, vol_prev = _prev_contract_bar(row["ticker"])
                    if _is_valid(px):
                        row["lastPrice"] = float(px)
                        if isinstance(vol_prev, int):
                            row["volume"] = vol_prev
                        fixed += 1
                        if fixed >= cap:
                            break
            return fixed
        backfilled_calls = _backfill(out_calls, cap=60)
        backfilled_puts  = _backfill(out_puts,  cap=60)

    out_calls.sort(key=lambda x: (x["strike"] is None, x["strike"]))
    out_puts.sort(key=lambda x: (x["strike"] is None, x["strike"]))

    return {
        "symbol": sym,
        "expiration": expiration,
        "calls": out_calls,
        "puts": out_puts,
        "metadata": {
            "source": "polygon-v3-snapshot-chain" + ("+prev-fill" if fill_zeros else ""),
            "pages": page,
            "prev_fill_applied": {"calls": backfilled_calls, "puts": backfilled_puts} if fill_zeros else {"calls": 0, "puts": 0},
            "mode": market_mode(),
        },
    }

def _chain_via_contracts_prev(sym: str, expiration: str) -> Dict[str, Any]:
    """
    Fallback when snapshot endpoint isn't available:
    - List contracts (v3)
    - Per-contract prev-day bar (v2) for lastPrice & volume; OI unavailable -> 0
    This is inherently EOD-style data.
    """
    url = "https://api.polygon.io/v3/reference/options/contracts"
    params = {
        "underlying_ticker": sym,
        "expiration_date": expiration,
        "limit": 1000,
        "sort": "strike_price",
        "order": "asc",
        "expired": "false",
    }
    j = _get(url, params)
    results = j.get("results") or []

    calls: List[Dict[str, Any]] = []
    puts: List[Dict[str, Any]] = []

    for r in results:
        ticker = r.get("ticker")
        strike = r.get("strike_price")
        ctype = (r.get("contract_type") or "").lower()

        last_px, vol = _prev_contract_bar(ticker) if ticker else (None, None)

        row = {
            "ticker": ticker,
            "strike": float(strike) if strike is not None else None,
            "lastPrice": float(last_px) if _is_valid(last_px) else 0.0,
            "volume": int(vol) if isinstance(vol, int) else 0,
            "openInterest": 0,
        }
        if ctype == "call":
            calls.append(row)
        elif ctype == "put":
            puts.append(row)

    calls.sort(key=lambda x: (x["strike"] is None, x["strike"]))
    puts.sort(key=lambda x: (x["strike"] is None, x["strike"]))

    return {
        "symbol": sym,
        "expiration": expiration,
        "calls": calls,
        "puts": puts,
        "metadata": {"source": "polygon-v3-contracts+v2-prev", "mode": market_mode()},
    }

# -------------------------- Public chain APIs --------------------------

def get_options_chain(symbol: str, expiration: str) -> Dict[str, Any]:
    """
    LIVE behavior:
      - Market OPEN  : snapshot only, DO NOT backfill zeros. lastPrice from last_trade.price
      - Market CLOSED: snapshot + backfill zeros from prev-day.
      - If snapshot unavailable: fall back to contracts+prev (EOD-style), labeled in metadata.
    """
    sym = symbol.upper().strip()
    mode = market_mode()
    if mode == "live":
        try:
            return _chain_via_snapshot(sym, expiration, fill_zeros=False)
        except Exception:
            data = _chain_via_contracts_prev(sym, expiration)
            data["metadata"]["note"] = "snapshot unavailable; using EOD fallback during live session"
            data["metadata"]["eod_fallback"] = True
            return data
    else:
        try:
            return _chain_via_snapshot(sym, expiration, fill_zeros=True)
        except Exception:
            return _chain_via_contracts_prev(sym, expiration)

def get_options_chain_eod(symbol: str, expiration: str) -> Dict[str, Any]:
    """
    Explicit EOD chain: always returns EOD-style data.
    - snapshot with prev-fill (fill zeros) when available
    - otherwise contracts+prev
    """
    sym = symbol.upper().strip()
    try:
        data = _chain_via_snapshot(sym, expiration, fill_zeros=True)
    except Exception:
        data = _chain_via_contracts_prev(sym, expiration)

    md = data.get("metadata", {})
    md["mode"] = "eod-forced"
    md["note"] = "explicit EOD chain"
    data["metadata"] = md
    return data

# -------------------------- Multiplexer some routes expect --------------------------

def get_options_data(symbol: Optional[str] = None, expiration: Optional[str] = None) -> Dict[str, Any]:
    if symbol and expiration:
        return get_options_chain(symbol, expiration)
    elif symbol:
        return get_options_expirations(symbol)
    return {"error": "symbol is required"}
