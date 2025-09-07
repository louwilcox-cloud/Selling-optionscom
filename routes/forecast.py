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
    """Run forecast for selected watchlist"""
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
        
        # Generate forecast results
        forecast_results = []
        start_date = datetime.now().strftime('%Y-%m-%d')
        
        for symbol in symbols:
            try:
                # Get current price
                quote_result = get_stock_quote(symbol)
                current_price = quote_result.get('price', 0) if 'error' not in quote_result else 0
                
                # Generate mock predictions for next 4 expirations
                predictions = []
                base_date = datetime.now()
                
                for i in range(4):
                    # Generate expiration date (simplified - 3rd Friday of each month)
                    exp_date = base_date + timedelta(days=21 * (i + 1))
                    exp_str = exp_date.strftime('%Y-%m-%d')
                    
                    # Mock prediction (in real implementation, use your prediction algorithm)
                    if current_price > 0:
                        # Simple random walk simulation for demo
                        import random
                        change_percent = random.uniform(-10, 10)  # -10% to +10%
                        predicted_price = current_price * (1 + change_percent / 100)
                    else:
                        predicted_price = 0
                        change_percent = 0
                    
                    predictions.append({
                        'expiration': exp_str,
                        'predicted_price': round(predicted_price, 2),
                        'percent_change': round(change_percent, 2)
                    })
                
                forecast_results.append({
                    'symbol': symbol,
                    'current_price': current_price,
                    'predictions': predictions
                })
                
            except Exception as e:
                # Add symbol with error message
                forecast_results.append({
                    'symbol': symbol,
                    'current_price': 0,
                    'predictions': [{'expiration': 'Error', 'predicted_price': 0, 'percent_change': 0}] * 4,
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'results': forecast_results,
            'start_date': start_date
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500