"""API routes for Selling-Options.com"""
import re
from flask import Blueprint, request, jsonify
from services.polygon_service import (
    get_stock_quote,
    get_market_phase,
    get_options_expirations,
    get_options_chain,
    get_options_chain_eod,  # explicit EOD chain
)
from utils.decorators import retry_with_backoff

api_bp = Blueprint("api", __name__, url_prefix="/api")

# --- symbol sanitizer (handles stray quotes, spaces, odd chars) ---
ALLOWED_TICKER_CHARS = re.compile(r"[^A-Za-z0-9\.\-:]+")

def _clean_symbol(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip().strip('\'"')
    s = ALLOWED_TICKER_CHARS.sub("", s)
    return s.upper()


@api_bp.route("/health")
def health_check():
    """Health check endpoint for container monitoring"""
    from datetime import datetime
    import os
    try:
        status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "polygon_api": "configured" if os.getenv("POLYGON_API_KEY") else "missing",
            "market_phase": get_market_phase(),
            "uptime": "running",
        }
        return jsonify(status), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e), "timestamp": datetime.now().isoformat()}), 500


@api_bp.route("/quote")
def quote():
    """Get stock quote for a symbol with fallback support (live during session, EOD otherwise)."""
    raw = request.args.get("symbol", "")
    symbol = _clean_symbol(raw)
    if not symbol:
        return jsonify({"error": "Missing 'symbol'"}), 400
    try:
        data = get_stock_quote(symbol)  # -> {symbol, mode, price, source, at}
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch quote for {symbol}", "detail": str(e)}), 502


@api_bp.route("/get_options_data")
def get_options_data():
    """Get options data for a symbol (live behavior; zeros during session are kept)."""
    raw_symbol = request.args.get("symbol") or ""
    symbol = _clean_symbol(raw_symbol)
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


@api_bp.route("/get_options_data_eod")
def get_options_data_eod():
    """
    Explicit EOD chain for a symbol (fills zero lastPrice from prev-day; stable across closed periods).
    Usage: /api/get_options_data_eod?symbol=AAPL&date=YYYY-MM-DD
    If date omitted, returns expirations (same as /get_options_data).
    """
    raw_symbol = request.args.get("symbol") or ""
    symbol = _clean_symbol(raw_symbol)
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
        result = get_options_chain_eod(symbol, date)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch EOD options chain: {e}"}), 500


@api_bp.route("/market-data")
@retry_with_backoff(max_retries=2, base_delay=1)
def market_data():
    """
    Market Pulse data:
      - During market OPEN: delayed/live price via get_stock_quote(); change vs yesterday's close.
      - When CLOSED: price is EOD prev close; change = 0.
      - Never fabricate numbers.
    """
    import requests, os

    # Reordered so GLD appears in the second row on desktop (GLD moved to end)
    market_symbols = [
        ("SPY", "S&P 500"),
        ("QQQ", "NASDAQ"),
        ("DIA", "Dow Jones"),
        ("IWM", "Russell 2000"),
        ("TLT", "TLT"),
        ("UUP", "US Dollar"),
        ("USO", "Oil"),
        ("GLD", "Gold"),
    ]

    api_key = os.getenv("POLYGON_API_KEY")
    items = []

    def prev_close(sym: str):
        try:
            url = f"https://api.polygon.io/v2/aggs/ticker/{sym}/prev"
            params = {"adjusted": "true", "apiKey": api_key}
            r = requests.get(url, params=params, timeout=5)
            if r.status_code == 200:
                j = r.json()
                if j.get("status") == "OK" and j.get("results"):
                    return float(j["results"][0].get("c") or 0)
        except Exception:
            pass
        return 0.0

    for symbol, display_name in market_symbols:
        try:
            price = None
            mode = None
            try:
                q = get_stock_quote(symbol)
                price = float(q["price"])
                mode = q.get("mode")
            except Exception:
                pc_tmp = prev_close(symbol)
                if pc_tmp > 0:
                    price = pc_tmp
                    mode = "eod"
                else:
                    raise

            pc = prev_close(symbol)  # yesterday close for change calc
            if price is None or price <= 0:
                raise RuntimeError("no_price")

            if mode == "live" and pc > 0:
                change = price - pc
                change_pct = (change / pc) * 100.0
            else:
                change = 0.0
                change_pct = 0.0

            items.append({
                "name": display_name,
                "price": round(price, 4),
                "change": round(change, 4),
                "change_pct": round(change_pct, 2),
            })

        except Exception:
            items.append({
                "name": display_name,
                "price": 0.0,
                "change": 0.0,
                "change_pct": 0.0,
            })

    return jsonify(items)


@api_bp.route("/auth-status")
def auth_status():
    """Get current authentication status"""
    from flask import session
    from services.database import get_db_connection

    if "user_id" not in session:
        return jsonify({"authenticated": False, "email": "", "is_admin": False})

    user_id = session["user_id"]
    email = session.get("email", "")

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

    return jsonify({"authenticated": True, "email": email, "is_admin": is_admin})


@api_bp.route("/results_both")
def results_both():
    """Calculate options sentiment predictions using volume/OI weighting"""
    symbol = _clean_symbol(request.args.get("symbol") or "")
    date = request.args.get("date") or request.args.get("expiration")
    if not symbol:
        return jsonify({"error": "Missing 'symbol' parameter"}), 400
    if not date:
        return jsonify({"error": "Missing 'date' or 'expiration' parameter"}), 400

    try:
        chain_data = get_options_chain(symbol, date)
        calls = chain_data.get("calls", [])
        puts = chain_data.get("puts", [])
        if not calls and not puts:
            return jsonify({"error": f"No options data available for {symbol} {date}"}), 404

        quote = get_stock_quote(symbol)  # centralized market mode
        current_price = float(quote["price"])

        all_options = []
        for call in calls:
            strike = float(call.get("strike", 0))
            premium = float(call.get("lastPrice", 0))
            volume = int(call.get("volume", 0))
            oi = int(call.get("openInterest", 0))
            if premium > 0:
                all_options.append({
                    "type": "call", "strike": strike, "premium": premium,
                    "volume": volume, "openInterest": oi,
                    "breakeven": strike + premium,
                })
        for put in puts:
            strike = float(put.get("strike", 0))
            premium = float(put.get("lastPrice", 0))
            volume = int(put.get("volume", 0))
            oi = int(put.get("openInterest", 0))
            if premium > 0:
                all_options.append({
                    "type": "put", "strike": strike, "premium": premium,
                    "volume": volume, "openInterest": oi,
                    "breakeven": strike - premium,
                })

        volume_rows = [o for o in all_options if o["volume"] > 0]
        oi_rows = [o for o in all_options if o["openInterest"] > 0]
        if not volume_rows and not oi_rows:
            return jsonify({"error": "No valid options data with volume or open interest"}), 404

        vol_prediction = None; vol_weight_sum = 0; vol_numerator = 0; vol_count = 0
        if volume_rows:
            for o in volume_rows:
                w = o["premium"] * o["volume"]
                vol_weight_sum += w
                vol_numerator += o["breakeven"] * w
                vol_count += 1
            if vol_weight_sum > 0:
                vol_prediction = vol_numerator / vol_weight_sum

        oi_prediction = None; oi_weight_sum = 0; oi_numerator = 0; oi_count = 0
        if oi_rows:
            for o in oi_rows:
                w = o["premium"] * o["openInterest"]
                oi_weight_sum += w
                oi_numerator += o["breakeven"] * w
                oi_count += 1
            if oi_weight_sum > 0:
                oi_prediction = oi_numerator / oi_weight_sum

        avg_prediction = None
        if vol_prediction is not None and oi_prediction is not None:
            avg_prediction = (vol_prediction + oi_prediction) / 2

        def pct(a, b): return ((a - b) / b) * 100 if (a is not None and b) else None

        return jsonify({
            "symbol": symbol,
            "expiration": date,
            "currentPrice": round(current_price, 2),
            "volume": {
                "prediction": round(vol_prediction, 6) if vol_prediction else None,
                "pctChange": round(pct(vol_prediction, current_price), 2) if vol_prediction else None,
                "weightSum": round(vol_weight_sum, 2),
                "contributingRows": vol_count,
            },
            "openInterest": {
                "prediction": round(oi_prediction, 6) if oi_prediction else None,
                "pctChange": round(pct(oi_prediction, current_price), 2) if oi_prediction else None,
                "weightSum": round(oi_weight_sum, 2),
                "contributingRows": oi_count,
            },
            "average": {
                "prediction": round(avg_prediction, 6) if avg_prediction else None,
                "pctChange": round(pct(avg_prediction, current_price), 2) if avg_prediction else None,
            },
            "debug": {
                "totalOptionsProcessed": len(all_options),
                "callsProcessed": len([o for o in all_options if o["type"] == "call"]),
                "putsProcessed": len([o for o in all_options if o["type"] == "put"]),
                "volumeWeightSum": vol_weight_sum,
                "oiWeightSum": oi_weight_sum,
            },
        })

    except Exception as e:
        import traceback
        print(f"Error in results_both for {symbol}: {e}")
        print(traceback.format_exc())
        return jsonify({"error": f"Calculation failed: {str(e)}"}), 500
