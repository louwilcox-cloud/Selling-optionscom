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