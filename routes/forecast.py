"""Forecast routes for Selling-Options.com"""
import re
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template
from services.database import get_db_connection
from services.polygon_service import get_stock_quote
from utils.decorators import login_required

forecast_bp = Blueprint('forecast', __name__)

@forecast_bp.route('/forecast')
def forecast():
    """Watchlist forecasting page"""
    conn = get_db_connection()
    if not conn:
        return "Database connection error", 500
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, symbols FROM watchlists ORDER BY name")
        watchlists = cur.fetchall()
        cur.close()
        conn.close()
        
        return render_template('forecast.html', watchlists=watchlists)
        
    except Exception as e:
        if conn:
            conn.close()
        return f"Error loading watchlists: {str(e)}", 500

@forecast_bp.route('/api/forecast', methods=['POST'])
def run_forecast():
    """Run forecast for selected watchlist using Bulls/Bears analysis"""
    try:
        data = request.get_json()
        watchlist_id = data.get('watchlist_id')
        
        if not watchlist_id:
            return jsonify({'success': False, 'error': 'Missing watchlist_id'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        
        try:
            cur = conn.cursor()
            cur.execute("SELECT symbols FROM watchlists WHERE id = %s", (watchlist_id,))
            result = cur.fetchone()
            cur.close()
            conn.close()
            
            if not result:
                return jsonify({'success': False, 'error': 'Watchlist not found'}), 404
            
            symbols_str = result[0]
            
        except Exception as e:
            if conn:
                conn.close()
            return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500
        
        # Parse symbols from comma/space separated string
        symbols = [s.strip().upper() for s in re.split(r'[,\\s]+', symbols_str) if s.strip()]
        
        # Import options service functions
        from services.polygon_service import get_options_expirations, get_options_chain
        
        # Generate forecast results with Bulls/Bears analysis
        forecast_results = []
        
        for symbol in symbols:
            try:
                # Get current price
                quote_result = get_stock_quote(symbol)
                current_price = quote_result.get('price', 0) if 'error' not in quote_result else 0
                
                if current_price <= 0:
                    forecast_results.append({
                        'symbol': symbol,
                        'current_price': 0,
                        'bulls_want': 0,
                        'bears_want': 0,
                        'avg_consensus': 0
                    })
                    continue
                
                # Get available expirations
                expirations_data = get_options_expirations(symbol)
                expirations = expirations_data.get('expirations', [])
                if not expirations:
                    forecast_results.append({
                        'symbol': symbol,
                        'current_price': current_price,
                        'bulls_want': current_price,
                        'bears_want': current_price,
                        'avg_consensus': current_price
                    })
                    continue
                
                # Use the first available expiration for analysis
                next_expiry = expirations[0]
                
                # Get options chain using EXACT same method as calculator
                chain_data = get_options_chain(symbol, next_expiry)
                all_calls = chain_data.get('calls', [])
                all_puts = chain_data.get('puts', [])
                
                # Filter to only valid options with non-zero prices (like calculator.js)
                calls = [c for c in all_calls if c.get('lastPrice', 0) > 0]
                puts = [p for p in all_puts if p.get('lastPrice', 0) > 0]
                
                # EXACT same logic as calculator.js lines 177-191
                def is_finite_num(x):
                    return isinstance(x, (int, float)) and not (x != x or x == float('inf') or x == float('-inf'))
                
                class WeightedMeanResult:
                    def __init__(self, value, total_weight):
                        self.value = value
                        self.total_weight = total_weight
                
                def weighted_mean(rows, value_fn, weight_fn):
                    """EXACT copy of calculator.js weightedMean function"""
                    total_w = 0
                    acc = 0
                    for r in rows:
                        v = value_fn(r)
                        w = weight_fn(r)
                        if not is_finite_num(v) or not is_finite_num(w) or w <= 0:
                            continue
                        acc += v * w
                        total_w += w
                    value = acc / total_w if total_w > 0 else float('nan')
                    return WeightedMeanResult(value, total_w)
                
                # EXACT same breakeven functions as calculator.js  
                def be_call(r):
                    return r.get('strike', 0) + r.get('lastPrice', 0)
                
                def be_put(r):
                    return r.get('strike', 0) - r.get('lastPrice', 0)
                
                # EXACT same weight functions as calculator.js
                def weight_vol(r):
                    return r.get('lastPrice', 0) * r.get('volume', 0)
                
                def weight_oi(r):
                    return r.get('lastPrice', 0) * r.get('openInterest', 0)
                
                # EXACT same calculation as calculator.js
                bulls_vol = weighted_mean(calls, be_call, weight_vol)
                bears_vol = weighted_mean(puts, be_put, weight_vol)
                bulls_oi = weighted_mean(calls, be_call, weight_oi)
                bears_oi = weighted_mean(puts, be_put, weight_oi)
                
                # EXACT same fallback logic as calculator.js (access .value property)
                bulls_want = bulls_vol.value if is_finite_num(bulls_vol.value) else bulls_oi.value
                bears_want = bears_vol.value if is_finite_num(bears_vol.value) else bears_oi.value
                
                # Handle case where values are None or non-finite (fallback to current price)
                if not is_finite_num(bulls_want):
                    bulls_want = current_price
                if not is_finite_num(bears_want):
                    bears_want = current_price
                
                # EXACT same consensus calculation as calculator.js
                if is_finite_num(bulls_want) and is_finite_num(bears_want):
                    avg_consensus = (bulls_want + bears_want) / 2
                else:
                    avg_consensus = current_price
                
                forecast_results.append({
                    'symbol': symbol,
                    'current_price': current_price,
                    'bulls_want': round(bulls_want, 2),
                    'bears_want': round(bears_want, 2),
                    'avg_consensus': round(avg_consensus, 2)
                })
                
            except Exception as e:
                # Add symbol with error message
                forecast_results.append({
                    'symbol': symbol,
                    'current_price': current_price if 'current_price' in locals() else 0,
                    'bulls_want': 0,
                    'bears_want': 0,
                    'avg_consensus': 0
                })
        
        # Return results directly (frontend expects array, not wrapped in success/results)
        return jsonify(forecast_results)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500