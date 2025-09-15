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
                        'bias': 'NO_DATA',
                        'expected_move': 0,
                        'next_expiry': 'N/A'
                    })
                    continue
                
                # Get available expirations
                expirations = get_options_expirations(symbol)
                if not expirations:
                    forecast_results.append({
                        'symbol': symbol,
                        'current_price': current_price,
                        'bulls_want': current_price,
                        'bears_want': current_price,
                        'bias': 'NO_OPTIONS',
                        'expected_move': 0,
                        'next_expiry': 'N/A'
                    })
                    continue
                
                # Use the first available expiration for analysis
                next_expiry = expirations[0]
                
                # Get options chain for Bulls/Bears analysis
                chain_data = get_options_chain(symbol, next_expiry)
                calls = chain_data.get('calls', [])
                puts = chain_data.get('puts', [])
                
                # Calculate Bulls/Bears values using same logic as calculator
                def calculate_weighted_mean(options, value_fn, weight_fn):
                    total_weight = 0
                    weighted_sum = 0
                    
                    for option in options:
                        value = value_fn(option)
                        weight = weight_fn(option)
                        
                        if value is not None and weight is not None and weight > 0:
                            weighted_sum += value * weight
                            total_weight += weight
                    
                    return weighted_sum / total_weight if total_weight > 0 else None
                
                # Calculate breakevens
                def call_breakeven(option):
                    return option.get('strike', 0) + option.get('lastPrice', 0)
                
                def put_breakeven(option):
                    return option.get('strike', 0) - option.get('lastPrice', 0)
                
                # Weight by dollar volume (prefer) or dollar OI (fallback)
                def volume_weight(option):
                    return option.get('lastPrice', 0) * option.get('volume', 0)
                
                def oi_weight(option):
                    return option.get('lastPrice', 0) * option.get('openInterest', 0)
                
                # Calculate Bulls target (calls weighted breakeven)
                bulls_vol = calculate_weighted_mean(calls, call_breakeven, volume_weight)
                bulls_oi = calculate_weighted_mean(calls, call_breakeven, oi_weight)
                bulls_want = bulls_vol if bulls_vol is not None else (bulls_oi if bulls_oi is not None else current_price)
                
                # Calculate Bears target (puts weighted breakeven)  
                bears_vol = calculate_weighted_mean(puts, put_breakeven, volume_weight)
                bears_oi = calculate_weighted_mean(puts, put_breakeven, oi_weight)
                bears_want = bears_vol if bears_vol is not None else (bears_oi if bears_oi is not None else current_price)
                
                # Determine bias and expected move
                if bulls_want > current_price and bears_want < current_price:
                    bias = 'NEUTRAL'
                    expected_move = (bulls_want - bears_want) / 2
                elif bulls_want > bears_want:
                    bias = 'BULLISH'  
                    expected_move = abs(bulls_want - current_price)
                else:
                    bias = 'BEARISH'
                    expected_move = abs(current_price - bears_want)
                
                forecast_results.append({
                    'symbol': symbol,
                    'current_price': current_price,
                    'bulls_want': round(bulls_want, 2),
                    'bears_want': round(bears_want, 2),
                    'bias': bias,
                    'expected_move': round(expected_move, 2),
                    'next_expiry': next_expiry
                })
                
            except Exception as e:
                # Add symbol with error message
                forecast_results.append({
                    'symbol': symbol,
                    'current_price': current_price if 'current_price' in locals() else 0,
                    'bulls_want': 0,
                    'bears_want': 0,
                    'bias': 'ERROR',
                    'expected_move': 0,
                    'next_expiry': f'Error: {str(e)}'
                })
        
        # Return results directly (frontend expects array, not wrapped in success/results)
        return jsonify(forecast_results)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500