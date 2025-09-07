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
    """Get stock quote for a symbol"""
    symbol = (request.args.get("symbol") or "").strip().upper()
    if not symbol:
        return jsonify({"error": "Missing 'symbol'"}), 400
    
    result = get_stock_quote(symbol)
    
    if "error" in result:
        return jsonify(result), 503
    
    return jsonify(result)

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
    """Get market data for dashboard"""
    # Placeholder for market data - in full implementation this would
    # call the existing market data functions from the original app.py
    market_data = {
        "S&P 500": {"price": 4200.0, "change": 25.5, "change_percent": 0.61},
        "Dow Jones": {"price": 34000.0, "change": -45.2, "change_percent": -0.13},
        "NASDAQ": {"price": 13500.0, "change": 85.3, "change_percent": 0.64},
        "Russell 2000": {"price": 2100.0, "change": 12.8, "change_percent": 0.61},
        "VIX": {"price": 18.5, "change": -1.2, "change_percent": -6.09},
        "Gold": {"price": 1950.0, "change": 8.5, "change_percent": 0.44},
        "TLT": {"price": 95.5, "change": -0.8, "change_percent": -0.83},
        "US Dollar": {"price": 102.3, "change": 0.2, "change_percent": 0.20},
        "Oil": {"price": 78.5, "change": 1.5, "change_percent": 1.95},
        "Tech": {"price": 145.0, "change": 2.1, "change_percent": 1.47}
    }
    
    return jsonify(market_data)

@api_bp.route('/auth-status')
def auth_status():
    """Get current authentication status"""
    from flask import session
    
    return jsonify({
        'authenticated': 'user_id' in session,
        'username': session.get('username', ''),
        'is_admin': session.get('username') == 'admin'
    })