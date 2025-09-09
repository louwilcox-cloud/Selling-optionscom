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
    """Get complete options chain for symbol and expiration date using Polygon contracts endpoint"""
    import requests
    import os
    from datetime import datetime, timedelta
    
    try:
        api_key = os.getenv("POLYGON_API_KEY")
        if not api_key:
            raise Exception("Polygon API key not found")
        
        market_phase = get_market_phase()
        print(f"📊 Fetching complete options chain for {symbol} {expiration_date} (market: {market_phase})")
        
        calls = []
        puts = []
        
        # Step 1: Get ALL option contracts for this expiration (both calls and puts)
        contracts_url = "https://api.polygon.io/v3/reference/options/contracts"
        
        # Make multiple requests to ensure we get ALL contracts
        all_contracts = []
        next_url = None
        page_count = 0
        
        while page_count < 10:  # Safety limit
            contracts_params = {
                "underlying_ticker": symbol,
                "expiration_date": expiration_date,
                "limit": 1000,  # Max allowed
                "order": "asc",
                "sort": "strike_price",
                "apikey": api_key
            }
            
            if next_url:
                # Use pagination if available
                contracts_response = requests.get(next_url, timeout=15)
            else:
                contracts_response = requests.get(contracts_url, params=contracts_params, timeout=15)
            
            if contracts_response.status_code != 200:
                print(f"❌ Contracts API error: {contracts_response.status_code}")
                break
                
            contracts_data = contracts_response.json()
            
            if contracts_data.get("status") != "OK":
                print(f"❌ Contracts API status: {contracts_data.get('status')}")
                break
                
            results = contracts_data.get("results", [])
            if not results:
                break
                
            all_contracts.extend(results)
            page_count += 1
            
            # Check for pagination
            next_url = contracts_data.get("next_url")
            if not next_url:
                break
                
        print(f"📋 Retrieved {len(all_contracts)} total contracts from {page_count} API pages")
        
        # Step 2: Separate calls and puts and get their trading data
        call_contracts = [c for c in all_contracts if c.get("contract_type") == "call"]
        put_contracts = [c for c in all_contracts if c.get("contract_type") == "put"]
        
        print(f"🔍 Contract breakdown: {len(call_contracts)} calls, {len(put_contracts)} puts")
        
        # Step 3: Get trading data for each contract
        def get_contract_data(contract):
            ticker = contract.get("ticker")
            strike_price = contract.get("strike_price")
            contract_type = contract.get("contract_type")
            
            if not ticker or not strike_price:
                return None
                
            # Try to get current/recent trading data
            last_price = 0
            volume = 0
            
            # Method 1: Try previous day aggregates first (most reliable for volume data)
            try:
                hist_url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev"
                hist_params = {"adjusted": "true", "apikey": api_key}
                
                hist_response = requests.get(hist_url, params=hist_params, timeout=3)
                if hist_response.status_code == 200:
                    hist_data = hist_response.json()
                    if hist_data.get("status") == "OK" and hist_data.get("results"):
                        result = hist_data["results"][0]
                        last_price = float(result.get("c", 0))  # Close price
                        volume = int(result.get("v", 0))        # Volume
            except:
                pass
                
            # Method 2: If no historical data, try current snapshot
            if last_price == 0:
                try:
                    snap_url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
                    snap_params = {"apikey": api_key}
                    
                    snap_response = requests.get(snap_url, params=snap_params, timeout=3)
                    if snap_response.status_code == 200:
                        snap_data = snap_response.json()
                        if snap_data.get("status") == "OK" and snap_data.get("ticker"):
                            ticker_data = snap_data["ticker"]
                            # Try various price fields
                            last_price = (ticker_data.get("day", {}) or {}).get("c") or \
                                        (ticker_data.get("lastTrade", {}) or {}).get("p") or \
                                        (ticker_data.get("prevDay", {}) or {}).get("c") or 0
                            volume = (ticker_data.get("day", {}) or {}).get("v") or 0
                            
                            if last_price:
                                last_price = float(last_price)
                            if volume:
                                volume = int(volume)
                except:
                    pass
            
            # Get open interest from contract metadata
            open_interest = int(contract.get("open_interest", 0))
            
            # Calculate bid/ask spread estimate
            if last_price > 0:
                spread_pct = 0.03 if last_price < 1 else 0.02 if last_price < 5 else 0.01
                bid = last_price * (1 - spread_pct)
                ask = last_price * (1 + spread_pct)
            else:
                # For options with no recent trading, use minimum values
                last_price = 0.01
                bid = 0.01
                ask = 0.02
                
            return {
                "strike": float(strike_price),
                "lastPrice": round(float(last_price), 2),
                "volume": int(volume),
                "openInterest": int(open_interest),
                "bid": round(float(bid), 2),
                "ask": round(float(ask), 2),
                "contractSymbol": ticker
            }
        
        # Process all call contracts
        print("📞 Processing call options...")
        for i, contract in enumerate(call_contracts):
            if i % 50 == 0:  # Progress indicator
                print(f"   Processed {i}/{len(call_contracts)} calls...")
            data = get_contract_data(contract)
            if data:
                calls.append(data)
                
        # Process all put contracts  
        print("📉 Processing put options...")
        for i, contract in enumerate(put_contracts):
            if i % 50 == 0:  # Progress indicator
                print(f"   Processed {i}/{len(put_contracts)} puts...")
            data = get_contract_data(contract)
            if data:
                puts.append(data)
        
        # Sort by strike price
        calls.sort(key=lambda x: x["strike"])
        puts.sort(key=lambda x: x["strike"])
        
        # Calculate comprehensive statistics
        total_call_volume = sum(c["volume"] for c in calls)
        total_put_volume = sum(p["volume"] for p in puts)
        total_call_oi = sum(c["openInterest"] for c in calls)
        total_put_oi = sum(p["openInterest"] for p in puts)
        
        # Count contracts with actual trading activity
        active_calls = len([c for c in calls if c["volume"] > 0 or c["openInterest"] > 0])
        active_puts = len([p for p in puts if p["volume"] > 0 or p["openInterest"] > 0])
        
        print(f"📈 Final Summary:")
        print(f"   Calls: {len(calls)} contracts ({active_calls} with activity)")
        print(f"   Puts: {len(puts)} contracts ({active_puts} with activity)")
        print(f"📊 Volume - Calls: {total_call_volume:,}, Puts: {total_put_volume:,}")
        print(f"📊 Open Interest - Calls: {total_call_oi:,}, Puts: {total_put_oi:,}")
        
        # Calculate P/C ratios
        volume_pc_ratio = round(total_put_volume / total_call_volume, 3) if total_call_volume > 0 else None
        oi_pc_ratio = round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else None
        
        print(f"📊 P/C Ratios - Volume: {volume_pc_ratio}, OI: {oi_pc_ratio}")
        
        return {
            "symbol": symbol,
            "date": expiration_date,
            "calls": calls,
            "puts": puts,
            "metadata": {
                "dataSource": "polygon-contracts",
                "marketPhase": market_phase,
                "totalCallVolume": total_call_volume,
                "totalPutVolume": total_put_volume,
                "totalCallOI": total_call_oi,
                "totalPutOI": total_put_oi,
                "volumePCRatio": volume_pc_ratio,
                "oiPCRatio": oi_pc_ratio,
                "activeCalls": active_calls,
                "activePuts": active_puts
            }
        }
                
    except Exception as e:
        print(f"❌ Error fetching options chain for {symbol} {expiration_date}: {e}")
        import traceback
        print(traceback.format_exc())
    
    # Return empty chain if API fails
    return {
        "symbol": symbol,
        "date": expiration_date,
        "calls": [],
        "puts": [],
        "metadata": {
            "dataSource": "failed",
            "marketPhase": "unknown"
        }
    }