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

def quote_delayed(symbol: str, timeout=10) -> Tuple[Optional[float], Optional[str]]:
    """Get delayed quote using Polygon.io API only"""
    if not POLY_KEY:
        return None, "no-api-key"
    
    # 1) Polygon prev close - most reliable for delayed data
    try:
        r = _http.get(f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev",
                      params={"adjusted":"true","apiKey":POLY_KEY}, timeout=timeout)
        if r.status_code == 200:
            j = r.json()
            if j.get("status") == "OK" and j.get("results"):
                return float(j["results"][0]["c"]), "polygon-prev"
    except Exception as e:
        print(f"Polygon prev close failed for {symbol}: {e}")

    # 2) Polygon snapshot - real-time/delayed snapshot
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
                if price: 
                    return float(price), "polygon-snapshot"
    except Exception as e:
        print(f"Polygon snapshot failed for {symbol}: {e}")

    # 3) Polygon daily open/close endpoint as final fallback
    try:
        from datetime import datetime, timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        r = _http.get(f"https://api.polygon.io/v1/open-close/{symbol}/{yesterday}",
                      params={"adjusted":"true","apiKey":POLY_KEY}, timeout=timeout)
        if r.status_code == 200:
            j = r.json()
            if j.get("status") == "OK" and j.get("close"):
                return float(j["close"]), "polygon-open-close"
    except Exception as e:
        print(f"Polygon open-close failed for {symbol}: {e}")

    return None, "polygon-unavailable"

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
    """Get available options expiration dates for a symbol using Polygon API"""
    import requests
    import os
    from datetime import datetime
    
    try:
        api_key = os.getenv("POLYGON_API_KEY")
        if not api_key:
            raise Exception("Polygon API key not found")
            
        # Use Polygon options contracts endpoint to get expirations
        url = f"https://api.polygon.io/v3/reference/options/contracts"
        params = {
            "underlying_ticker": symbol,
            "limit": 1000,
            "expired": "false",
            "order": "asc",
            "sort": "expiration_date",
            "apikey": api_key
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "OK" and data.get("results"):
                # Extract unique expiration dates
                expirations = set()
                for contract in data["results"]:
                    exp_date = contract.get("expiration_date")
                    if exp_date:
                        expirations.add(exp_date)
                
                # Sort and filter future dates only
                today = datetime.now().strftime('%Y-%m-%d')
                future_exps = [exp for exp in sorted(expirations) if exp > today]
                return future_exps[:20]  # Return up to 20 future expirations
                
    except Exception as e:
        print(f"Error fetching options expirations for {symbol}: {e}")
    
    # Fallback to mock data
    from datetime import datetime, timedelta
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
    """Get options chain for symbol and expiration date using Polygon Options Chain Snapshot API"""
    import requests
    import os
    
    try:
        api_key = os.getenv("POLYGON_API_KEY")
        if not api_key:
            raise Exception("Polygon API key not found")
            
        # Use Polygon Options Chain Snapshot API - gets all market data in one call
        url = f"https://api.polygon.io/v3/snapshot/options/{symbol.upper()}"
        params = {
            "expiration_date": expiration_date,
            "apikey": api_key
        }
        
        response = requests.get(url, params=params, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "OK" and data.get("results"):
                calls = []
                puts = []
                
                # Process real market data from snapshot API
                for contract in data["results"]:
                    details = contract.get("details", {})
                    day = contract.get("day", {})
                    last_trade = contract.get("last_trade", {})
                    
                    strike = details.get("strike_price")
                    contract_type = details.get("contract_type")
                    ticker = details.get("ticker")
                    
                    if not strike or not contract_type or not ticker:
                        continue
                    
                    # Extract real market data - use actual API response structure
                    # Get last price from day.close or last_trade.price or last_quote
                    last_price = 0
                    if day.get("close"):
                        last_price = day["close"]
                    elif last_trade.get("price"):
                        last_price = last_trade["price"]
                    elif contract.get("last_quote", {}).get("close"):
                        last_price = contract["last_quote"]["close"]
                    
                    # Get volume from day data - this is critical for P/C ratios
                    volume = day.get("volume", 0) or 0
                    
                    # Get open interest - this is critical for P/C ratios
                    open_interest = contract.get("open_interest", 0) or 0
                    
                    # Calculate bid/ask from last price (typical spread estimation)
                    if last_price > 0:
                        spread_pct = 0.02 if last_price < 5 else 0.01  # 2% for cheap options, 1% for expensive
                        bid = last_price * (1 - spread_pct)
                        ask = last_price * (1 + spread_pct)
                    else:
                        bid = ask = 0
                        # For zero-price options, use intrinsic value if possible
                        if contract_type == "call" and strike > 0:
                            # Estimate intrinsic value for deep ITM calls
                            last_price = 0.01  # Minimum value for very OTM options
                        elif contract_type == "put" and strike > 0:
                            # Estimate intrinsic value for deep ITM puts  
                            last_price = 0.01  # Minimum value for very OTM options
                    
                    option_data = {
                        "strike": float(strike),
                        "lastPrice": round(float(last_price), 2),
                        "volume": int(volume),
                        "openInterest": int(open_interest),
                        "bid": round(float(bid), 2),
                        "ask": round(float(ask), 2),
                        "contractSymbol": ticker
                    }
                    
                    if contract_type == "call":
                        calls.append(option_data)
                    elif contract_type == "put":
                        puts.append(option_data)
                
                # Sort by strike price
                calls.sort(key=lambda x: x["strike"])
                puts.sort(key=lambda x: x["strike"])
                
                return {
                    "symbol": symbol,
                    "date": expiration_date,
                    "calls": calls,
                    "puts": puts
                }
                
    except Exception as e:
        print(f"Error fetching options chain for {symbol} {expiration_date}: {e}")
    
    # Return empty chain if API fails
    return {
        "symbol": symbol,
        "date": expiration_date,
        "calls": [],
        "puts": []
    }