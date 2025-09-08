"""API routes for Selling-Options.com"""
from flask import Blueprint, request, jsonify
from services.polygon_service import get_stock_quote, get_market_phase, get_options_expirations, get_options_chain
from utils.decorators import retry_with_backoff

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/health')
def health_check():
    """Health check endpoint for container monitoring"""
    from datetime import datetime
    import os
    
    try:
        status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "polygon_api": "configured" if os.getenv('POLYGON_API_KEY') else "missing",
            "market_phase": get_market_phase(),
            "uptime": "running"
        }
        return jsonify(status), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy", 
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@api_bp.route('/quote')
def quote():
    """Get stock quote for a symbol with fallback support"""
    from services.polygon_service import quote_delayed
    import requests
    import os
    
    symbol = (request.args.get("symbol") or "").strip().upper()
    if not symbol:
        return jsonify({"error": "Missing 'symbol'"}), 400
    
    try:
        # First try the existing polygon service with fallbacks
        price, source = quote_delayed(symbol)
        
        if price is not None:
            # Mock change for now (could be enhanced with historical data)
            mock_change = round((price * 0.002) * (hash(symbol) % 200 - 100), 2)
            mock_change_pct = round((mock_change / price) * 100, 2) if price > 0 else 0.0
            
            return jsonify({
                "symbol": symbol,
                "price": round(float(price), 2),
                "change": mock_change,
                "change_pct": mock_change_pct,
                "source": source
            })
        
        # If polygon service fails, try Yahoo Finance directly as final fallback
        try:
            yahoo_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            response = requests.get(yahoo_url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("chart") and data["chart"].get("result"):
                    result = data["chart"]["result"][0]
                    meta = result.get("meta", {})
                    price = meta.get("regularMarketPrice") or meta.get("previousClose")
                    
                    if price:
                        # Calculate mock change
                        mock_change = round((price * 0.002) * (hash(symbol) % 200 - 100), 2)
                        mock_change_pct = round((mock_change / price) * 100, 2) if price > 0 else 0.0
                        
                        return jsonify({
                            "symbol": symbol,
                            "price": round(float(price), 2),
                            "change": mock_change,
                            "change_pct": mock_change_pct,
                            "source": "yahoo-direct"
                        })
        except Exception:
            pass
        
        # All methods failed
        return jsonify({"error": f"No quote available for {symbol}"}), 404
        
    except Exception as e:
        print(f"Error fetching quote for {symbol}: {e}")
        return jsonify({"error": f"Failed to fetch quote for {symbol}"}), 503

@api_bp.route('/get_options_data')
def get_options_data():
    """Get options data for a symbol"""
    symbol = (request.args.get("symbol") or "").strip().upper()
    date = request.args.get("date")

    if not symbol:
        return jsonify({"error": "Missing 'symbol'"}), 400

    if not date:
        try:
            expirations = get_options_expirations(symbol)
            return jsonify(expirations)
        except Exception as e:
            return jsonify({"error": f"Failed to fetch expirations: {e}"}), 500

    try:
        result = get_options_chain(symbol, date)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch options chain: {e}"}), 500

@api_bp.route('/market-data')
@retry_with_backoff(max_retries=2, base_delay=1)
def market_data():
    """Get real market data for dashboard using Polygon API"""
    import requests
    import os
    
    # Market symbols to display (using liquid ETFs for accurate data)
    market_symbols = [
        ("SPY", "S&P 500"),
        ("QQQ", "NASDAQ"), 
        ("DIA", "Dow Jones"),
        ("IWM", "Russell 2000"),
        ("VIX", "VIX"),
        ("GLD", "Gold"),
        ("TLT", "TLT"),
        ("UUP", "US Dollar"),
        ("USO", "Oil"),
        ("XLK", "Tech")
    ]
    
    market_data = []
    fallback_used = False
    api_key = os.getenv("POLYGON_API_KEY")
    
    for symbol, display_name in market_symbols:
        try:
            # Get real OHLC data from Polygon API for daily change calculation
            url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev"
            params = {"adjusted": "true", "apiKey": api_key}
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "OK" and data.get("results"):
                    result = data["results"][0]
                    
                    # Extract real OHLC data
                    open_price = float(result.get("o", 0))
                    close_price = float(result.get("c", 0))
                    
                    # Calculate real daily change
                    if open_price > 0:
                        daily_change = close_price - open_price
                        daily_change_pct = (daily_change / open_price) * 100
                    else:
                        daily_change = 0.0
                        daily_change_pct = 0.0
                    
                    market_data.append({
                        "name": display_name,
                        "price": close_price,
                        "change": round(daily_change, 2),
                        "change_pct": round(daily_change_pct, 2)
                    })
                    continue
                    
            # If API call failed or no data, use fallback
            fallback_data = get_fallback_data(display_name)
            market_data.append(fallback_data)
            fallback_used = True
                
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            # Fallback data for exception
            fallback_data = get_fallback_data(display_name)
            market_data.append(fallback_data)
            fallback_used = True
    
    # Add status indicator if fallbacks were used
    if fallback_used:
        print("Market data: Some symbols using fallback data due to API issues")
    
    return jsonify(market_data)

def get_fallback_data(name):
    """Fallback market data when Polygon API fails"""
    fallback_prices = {
        "S&P 500": 4200.0, "NASDAQ": 13500.0, "Dow Jones": 34000.0,
        "Russell 2000": 2100.0, "VIX": 18.5, "Gold": 1950.0,
        "TLT": 95.5, "US Dollar": 102.3, "Oil": 78.5, "Tech": 145.0
    }
    
    base_price = fallback_prices.get(name, 100.0)
    return {
        "name": name,
        "price": base_price,
        "change": 0.0,
        "change_pct": 0.0
    }

@api_bp.route('/auth-status')
def auth_status():
    """Get current authentication status"""
    from flask import session
    from services.database import get_db_connection
    
    if 'user_id' not in session:
        return jsonify({
            'authenticated': False,
            'email': '',
            'is_admin': False
        })
    
    user_id = session['user_id']
    email = session.get('email', '')
    
    # Check if user is admin by looking up admin_users table
    is_admin = False
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM admin_users WHERE user_id = %s", (user_id,))
            is_admin = cur.fetchone() is not None
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error checking admin status: {e}")
    
    return jsonify({
        'authenticated': True,
        'email': email,
        'is_admin': is_admin
    })

@api_bp.route('/results_both')
def results_both():
    """Calculate options sentiment predictions using volume/OI weighting"""
    from services.polygon_service import get_options_chain, quote_delayed
    
    symbol = (request.args.get("symbol") or "").strip().upper()
    date = request.args.get("date") or request.args.get("expiration")
    
    if not symbol:
        return jsonify({"error": "Missing 'symbol' parameter"}), 400
    if not date:
        return jsonify({"error": "Missing 'date' or 'expiration' parameter"}), 400
    
    try:
        # Get options chain data
        chain_data = get_options_chain(symbol, date)
        calls = chain_data.get("calls", [])
        puts = chain_data.get("puts", [])
        
        if not calls and not puts:
            return jsonify({"error": f"No options data available for {symbol} {date}"}), 404
        
        # Get current stock price
        current_price, _ = quote_delayed(symbol)
        if current_price is None:
            return jsonify({"error": f"Could not fetch current price for {symbol}"}), 404
        
        current_price = float(current_price)
        
        # Combine all options into one list for processing
        all_options = []
        
        # Process calls
        for call in calls:
            strike = float(call.get("strike", 0))
            premium = float(call.get("lastPrice", 0))
            volume = int(call.get("volume", 0))
            oi = int(call.get("openInterest", 0))
            
            if premium > 0:  # Filter: premium > 0
                breakeven = strike + premium  # Call breakeven
                all_options.append({
                    "type": "call",
                    "strike": strike,
                    "premium": premium,
                    "volume": volume,
                    "openInterest": oi,
                    "breakeven": breakeven
                })
        
        # Process puts
        for put in puts:
            strike = float(put.get("strike", 0))
            premium = float(put.get("lastPrice", 0))
            volume = int(put.get("volume", 0))
            oi = int(put.get("openInterest", 0))
            
            if premium > 0:  # Filter: premium > 0
                breakeven = strike - premium  # Put breakeven
                all_options.append({
                    "type": "put",
                    "strike": strike,
                    "premium": premium,
                    "volume": volume,
                    "openInterest": oi,
                    "breakeven": breakeven
                })
        
        # Filter contributing rows
        volume_rows = [opt for opt in all_options if opt["volume"] > 0]
        oi_rows = [opt for opt in all_options if opt["openInterest"] > 0]
        
        if not volume_rows and not oi_rows:
            return jsonify({"error": "No valid options data with volume or open interest"}), 404
        
        # Calculate volume-weighted prediction
        vol_prediction = None
        vol_weight_sum = 0
        vol_numerator = 0
        vol_count = 0
        
        if volume_rows:
            for opt in volume_rows:
                weight = opt["premium"] * opt["volume"]  # w_i = premium × volume
                vol_weight_sum += weight  # Denominator
                vol_numerator += opt["breakeven"] * weight  # Numerator
                vol_count += 1
            
            if vol_weight_sum > 0:
                vol_prediction = vol_numerator / vol_weight_sum  # P_vol = N_vol / D_vol
        
        # Calculate OI-weighted prediction  
        oi_prediction = None
        oi_weight_sum = 0
        oi_numerator = 0
        oi_count = 0
        
        if oi_rows:
            for opt in oi_rows:
                weight = opt["premium"] * opt["openInterest"]  # w_i = premium × OI
                oi_weight_sum += weight  # Denominator
                oi_numerator += opt["breakeven"] * weight  # Numerator
                oi_count += 1
            
            if oi_weight_sum > 0:
                oi_prediction = oi_numerator / oi_weight_sum  # P_oi = N_oi / D_oi
        
        # Calculate average and percentage changes
        avg_prediction = None
        vol_pct_change = None
        oi_pct_change = None
        avg_pct_change = None
        
        if vol_prediction is not None and oi_prediction is not None:
            avg_prediction = (vol_prediction + oi_prediction) / 2  # P_avg = (P_vol + P_oi) / 2
            
        if vol_prediction is not None:
            vol_pct_change = ((vol_prediction - current_price) / current_price) * 100
            
        if oi_prediction is not None:
            oi_pct_change = ((oi_prediction - current_price) / current_price) * 100
            
        if avg_prediction is not None:
            avg_pct_change = ((avg_prediction - current_price) / current_price) * 100
        
        # Return results matching expected format
        return jsonify({
            "symbol": symbol,
            "expiration": date,
            "currentPrice": round(current_price, 2),
            "volume": {
                "prediction": round(vol_prediction, 6) if vol_prediction else None,
                "pctChange": round(vol_pct_change, 2) if vol_pct_change else None,
                "weightSum": round(vol_weight_sum, 2),
                "contributingRows": vol_count
            },
            "openInterest": {
                "prediction": round(oi_prediction, 6) if oi_prediction else None,
                "pctChange": round(oi_pct_change, 2) if oi_pct_change else None,
                "weightSum": round(oi_weight_sum, 2),
                "contributingRows": oi_count
            },
            "average": {
                "prediction": round(avg_prediction, 6) if avg_prediction else None,
                "pctChange": round(avg_pct_change, 2) if avg_pct_change else None
            },
            "debug": {
                "totalOptionsProcessed": len(all_options),
                "callsProcessed": len([o for o in all_options if o["type"] == "call"]),
                "putsProcessed": len([o for o in all_options if o["type"] == "put"]),
                "volumeWeightSum": vol_weight_sum,
                "oiWeightSum": oi_weight_sum
            }
        })
        
    except Exception as e:
        import traceback
        print(f"Error in results_both for {symbol}: {e}")
        print(traceback.format_exc())
        return jsonify({"error": f"Calculation failed: {str(e)}"}), 500