"""Polygon.io API service for Selling-Options.com"""
import os
import time
import requests
from typing import Tuple, Optional, List, Dict

# Configuration
POLY_KEY = os.getenv("POLYGON_API_KEY")
_http = requests.Session()
_http.headers["Accept-Encoding"] = "gzip"

# Market status cache
_status_cache = {"at": 0, "data": None}

def get_market_phase(ttl=15) -> str:
    """Return one of: 'open', 'afterhours', 'pre', 'closed' (ET clock)."""
    import datetime as dt
    
    now = time.time()
    if now - _status_cache["at"] < ttl and _status_cache["data"]:
        return _status_cache["data"]
    
    try:
        r = _http.get("https://api.polygon.io/v1/marketstatus/now",
                      params={"apiKey": POLY_KEY}, timeout=3)
        phase = "closed"
        if r.ok:
            j = r.json()
            # polygon returns 'market': 'open' or 'closed'; 'afterHours' boolean.
            if j.get("market") == "open":
                phase = "open"
            elif j.get("afterHours"):
                phase = "afterhours"
            else:
                # crude pre-market check based on ET hour (optional)
                et = dt.datetime.now(dt.timezone(dt.timedelta(hours=-4)))  # EDT
                if et.hour < 9 or (et.hour == 9 and et.minute < 30):
                    phase = "pre"
                else:
                    phase = "closed"
        _status_cache.update({"at": now, "data": phase})
        return phase
    except Exception as e:
        print(f"Market status check failed: {e}")
        # Default to closed if we can't determine status
        return "closed"

def quote_delayed(symbol: str, timeout=5) -> Tuple[Optional[float], Optional[str]]:
    """Reliable delayed quote with multiple fallbacks - never hangs"""
    # 1) Polygon prev close
    try:
        r = _http.get(f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev",
                      params={"adjusted":"true","apiKey":POLY_KEY}, timeout=timeout)
        if r.status_code == 200:
            j = r.json()
            if j.get("status") == "OK" and j.get("results"):
                return float(j["results"][0]["c"]), "polygon-prev"
    except Exception:
        pass

    # 2) Polygon snapshot
    try:
        r = _http.get(f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}",
                      params={"apiKey":POLY_KEY}, timeout=timeout)
        if r.status_code == 200:
            j = r.json()
            if j.get("status") == "OK" and j.get("ticker"):
                t = j["ticker"]
                price = (t.get("prevDay",{}) or {}).get("c") \
                        or (t.get("lastTrade",{}) or {}).get("p") \
                        or (t.get("day",{}) or {}).get("c")
                if price: return float(price), "polygon-snapshot"
    except Exception:
        pass

    # 3) Yahoo Finance fallback
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/download/{symbol}?period1=1640995200&period2=9999999999&interval=1d&events=history"
        r = _http.get(url, timeout=timeout)
        if r.ok and "Date,Open,High,Low,Close" in r.text:
            lines = [ln for ln in r.text.splitlines() if ln and not ln.startswith("Date,") and "," in ln]
            if lines:
                try:
                    close = float(lines[-1].split(",")[4])  # Close price
                    return close, "yahoo-eod"
                except (ValueError, IndexError):
                    pass
    except Exception:
        pass

    return None, None

def get_stock_quote(symbol: str) -> Dict:
    """Get stock quote with market context"""
    price, source = quote_delayed(symbol)
    
    if price is None:
        return {
            "error": "No price available",
            "symbol": symbol
        }
    
    return {
        "symbol": symbol,
        "price": round(float(price), 4),
        "source": source,
        "note": "Delayed/EOD price; shows previous session close when market is closed."
    }

def get_options_expirations(symbol: str) -> List[str]:
    """Get available options expiration dates for a symbol"""
    # Placeholder for now - in full implementation this would call Polygon API
    # or use the existing _fetch_expirations function
    from datetime import datetime, timedelta
    
    # Generate next 4 monthly expirations as example
    base_date = datetime.now()
    expirations = []
    
    for i in range(4):
        # Third Friday of each month (simplified)
        month = base_date.month + i
        year = base_date.year
        if month > 12:
            month -= 12
            year += 1
        
        # Find third Friday (simplified calculation)
        first_day = datetime(year, month, 1)
        first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
        third_friday = first_friday + timedelta(days=14)
        
        expirations.append(third_friday.strftime('%Y-%m-%d'))
    
    return expirations

def get_options_chain(symbol: str, expiration_date: str) -> Dict:
    """Get options chain for symbol and expiration date"""
    # Placeholder for now - in full implementation this would call Polygon API
    # or use the existing _fetch_chain function
    return {
        "symbol": symbol,
        "date": expiration_date,
        "calls": [],
        "puts": []
    }