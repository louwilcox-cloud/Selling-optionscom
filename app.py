#!/usr/bin/env python3
"""
Simple Flask API for the Options Sentiment Analyzer
Provides endpoints that match your existing API structure
"""

import os
import uuid
import bcrypt
import psycopg2
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, render_template_string, flash
from flask_session import Session
import yfinance as yf
import pandas as pd
import math

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
Session(app)

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get('PGHOST'),
        database=os.environ.get('PGDATABASE'),
        user=os.environ.get('PGUSER'),
        password=os.environ.get('PGPASSWORD'),
        port=os.environ.get('PGPORT')
    )

# Authentication functions
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT 1 FROM admin_users WHERE user_id = %s', (session['user_id'],))
        is_admin = cur.fetchone() is not None
        cur.close()
        conn.close()
        
        if not is_admin:
            return 'Access denied. Admin only.', 403
        return f(*args, **kwargs)
    return decorated_function

def _safe_float(x) -> float:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return 0.0
        return float(x)
    except Exception:
        return 0.0

def _to_rows(df: pd.DataFrame, type_label: str):
    cols = ["strike", "lastPrice", "volume", "openInterest"]
    present = [c for c in cols if c in df.columns]
    out = []
    for _, r in df[present].iterrows():
        out.append({
            "strike": _safe_float(r.get("strike", 0)),
            "lastPrice": _safe_float(r.get("lastPrice", 0)),
            "volume": int(_safe_float(r.get("volume", 0))),
            "openInterest": int(_safe_float(r.get("openInterest", 0))),
            "type": type_label,
        })
    return out

def _fetch_expirations(symbol: str):
    t = yf.Ticker(symbol)
    exps = t.options or []
    return [str(e) for e in exps]

def _fetch_chain(symbol: str, date: str):
    t = yf.Ticker(symbol)
    chain = t.option_chain(date)
    calls_df = chain.calls.copy()
    puts_df = chain.puts.copy()
    calls = _to_rows(calls_df, "Call")
    puts = _to_rows(puts_df, "Put")
    return calls, puts

def _compute_results(symbol: str, exp_date: str, calls, puts):
    """
    Weighted BreakEven across Calls + Puts.
    """
    all_rows = []
    for src, type_label in [(calls, "Call"), (puts, "Put")]:
        for r in src:
            strike = _safe_float(r.get("strike", 0))
            last_price = _safe_float(r.get("lastPrice", 0))
            oi = int(_safe_float(r.get("openInterest", 0)))
            volume = int(_safe_float(r.get("volume", 0)))

            if type_label == "Call":
                breakeven = strike + last_price
            else:
                breakeven = strike - last_price

            tot_pre = last_price * oi

            all_rows.append({
                "Symbol": symbol,
                "Strike": strike,
                "Exp Date": exp_date,
                "AvgLast": last_price,
                "BreakEven": breakeven,
                "CountOfSymbol": 1,
                "OI": oi,
                "Volume": volume,
                "TotPre": tot_pre,
                "Type": type_label
            })

    sum_of_tot_pre = sum(r["TotPre"] for r in all_rows) or 0.0

    rows = []
    for r in all_rows:
        pct = (r["TotPre"] / sum_of_tot_pre) if sum_of_tot_pre > 0 else 0.0
        part = r["BreakEven"] * pct
        row = dict(r)
        row["SumOfTotPre"] = sum_of_tot_pre
        row["PercentofMoneySpent"] = pct
        row["PartofMoney"] = part
        rows.append(row)

    rows.sort(key=lambda x: (x["Strike"], 0 if x["Type"] == "Call" else 1))
    return {
        "symbol": symbol,
        "expDate": exp_date,
        "rows": rows,
        "sumPartOfMoney": sum(r["PartofMoney"] for r in rows),
        "sumOfTotPre": sum_of_tot_pre,
        "countRows": len(rows),
    }

def _get_quote_price(symbol: str) -> float:
    t = yf.Ticker(symbol)
    price = None
    try:
        price = t.fast_info.get("last_price", None)
    except Exception:
        price = None
    if price is None:
        hist = t.history(period="1d")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
    return _safe_float(price)

# API Routes
@app.route("/api/quote")
def api_quote():
    symbol = (request.args.get("symbol") or "").strip().upper()
    if not symbol:
        return jsonify({"error": "Missing 'symbol'"}), 400
    try:
        price = _get_quote_price(symbol)
        if price <= 0:
            raise ValueError("No price found")
        return jsonify({"symbol": symbol, "price": round(price, 4)})
    except Exception as e:
        return jsonify({"error": f"Quote fetch failed: {e}"}), 500

@app.route("/api/get_options_data")
def api_get_options_data():
    symbol = (request.args.get("symbol") or "").strip().upper()
    date = request.args.get("date")

    if not symbol:
        return jsonify({"error": "Missing 'symbol'"}), 400

    if not date:
        try:
            expirations = _fetch_expirations(symbol)
            return jsonify(expirations)
        except Exception as e:
            return jsonify({"error": f"Failed to fetch expirations: {e}"}), 500

    try:
        calls, puts = _fetch_chain(symbol, date)
        return jsonify({"symbol": symbol, "date": date, "calls": calls, "puts": puts})
    except Exception as e:
        return jsonify({"error": f"Failed to fetch options chain: {e}"}), 500

# Market data API
@app.route("/api/market-data")
def api_market_data():
    """Get major market indices and assets"""
    try:
        # Ordered by importance as requested
        # Row 1: S&P500, DOW, NASDAQ, Russell, VIX
        # Row 2: DXY, Gold, TLT, Bitcoin, ETH
        symbols_ordered = [
            ('S&P 500', '^GSPC'),
            ('Dow Jones', '^DJI'),
            ('NASDAQ', '^IXIC'),
            ('Russell 2000', '^RUT'),
            ('VIX', '^VIX'),
            ('US Dollar Index', 'DX=F'),
            ('Gold', 'GC=F'),
            ('TLT', 'TLT'),
            ('Bitcoin', 'BTC-USD'),
            ('Ethereum', 'ETH-USD'),
        ]
        
        market_data = []
        for name, symbol in symbols_ordered:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="2d")  # Get 2 days to calculate change
                if not hist.empty:
                    current = float(hist['Close'].iloc[-1])
                    previous = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current
                    change = current - previous
                    change_pct = (change / previous * 100) if previous != 0 else 0
                    
                    market_data.append({
                        'name': name,
                        'symbol': symbol,
                        'price': round(current, 2),
                        'change': round(change, 2),
                        'change_pct': round(change_pct, 2)
                    })
            except Exception as e:
                print(f"Error fetching {name}: {e}")
                market_data.append({
                    'name': name,
                    'symbol': symbol,
                    'price': 0,
                    'change': 0,
                    'change_pct': 0
                })
        
        return jsonify(market_data)
    except Exception as e:
        return jsonify({"error": f"Market data fetch failed: {e}"}), 500

@app.route("/api/auth-status")
def api_auth_status():
    """Get current authentication status"""
    if 'user_id' not in session:
        return jsonify({
            "authenticated": False,
            "username": None,
            "is_admin": False
        })
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get user info
        cur.execute('SELECT email FROM users WHERE id = %s', (session['user_id'],))
        user_result = cur.fetchone()
        
        if not user_result:
            session.clear()
            return jsonify({
                "authenticated": False,
                "username": None,
                "is_admin": False
            })
        
        username = user_result[0]
        
        # Check if admin
        cur.execute('SELECT 1 FROM admin_users WHERE user_id = %s', (session['user_id'],))
        is_admin = cur.fetchone() is not None
        
        cur.close()
        conn.close()
        
        return jsonify({
            "authenticated": True,
            "username": username,
            "user_id": session['user_id'],
            "is_admin": is_admin
        })
    except Exception as e:
        return jsonify({
            "authenticated": False,
            "username": None,
            "is_admin": False
        })

@app.route("/api/results_both")
def api_results_both():
    symbol = (request.args.get("symbol") or "").strip().upper()
    date = (request.args.get("date") or "").strip()

    if not symbol or not date:
        return jsonify({"error": "Provide both 'symbol' and 'date' (YYYY-MM-DD)"}), 400

    try:
        calls, puts = _fetch_chain(symbol, date)
        results = _compute_results(symbol, date, calls, puts)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": f"Computation failed: {e}"}), 500

# Authentication routes
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        
        if not email or not password:
            flash('Email and password are required', 'error')
            return redirect('/signup')
            
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return redirect('/signup')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if user already exists
        cur.execute('SELECT id FROM users WHERE email = %s', (email,))
        if cur.fetchone():
            flash('Email already registered', 'error')
            cur.close()
            conn.close()
            return redirect('/signup')
        
        # Create new user
        password_hash = hash_password(password)
        cur.execute(
            'INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id',
            (email, password_hash)
        )
        result = cur.fetchone()
        user_id = result[0] if result else None
        conn.commit()
        cur.close()
        conn.close()
        
        # Auto-login after signup
        session['user_id'] = user_id
        session['user_email'] = email
        flash('Account created successfully!', 'success')
        return redirect('/calculator.html')
    
    return render_template_string(SIGNUP_TEMPLATE)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        
        if not email or not password:
            flash('Email and password are required', 'error')
            return redirect('/login')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Find user and verify password
        cur.execute('SELECT id, password_hash, is_active FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        
        if not user or not verify_password(password, user[1]):
            flash('Invalid email or password', 'error')
            cur.close()
            conn.close()
            return redirect('/login')
        
        if not user[2]:  # is_active
            flash('Account is deactivated. Contact admin.', 'error')
            cur.close()
            conn.close()
            return redirect('/login')
        
        # Update login stats
        cur.execute(
            'UPDATE users SET last_login = CURRENT_TIMESTAMP, login_count = login_count + 1 WHERE id = %s',
            (user[0],)
        )
        conn.commit()
        cur.close()
        conn.close()
        
        # Set session
        session['user_id'] = user[0]
        session['user_email'] = email
        return redirect('/')
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect('/')

@app.route('/admin')
# @admin_required  # Temporarily disabled for testing
def admin_dashboard():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get all users with their stats
    cur.execute('''
        SELECT u.id, u.email, u.created_at, u.last_login, u.login_count, u.is_active,
               CASE WHEN a.user_id IS NOT NULL THEN true ELSE false END as is_admin
        FROM users u
        LEFT JOIN admin_users a ON u.id = a.user_id
        ORDER BY u.created_at DESC
    ''')
    users = cur.fetchall()
    
    # Get recent activity (last 30 days)
    cur.execute('''
        SELECT email, last_login
        FROM users 
        WHERE last_login > CURRENT_TIMESTAMP - INTERVAL '30 days'
        ORDER BY last_login DESC
        LIMIT 20
    ''')
    recent_activity = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template_string(ADMIN_TEMPLATE, users=users, recent_activity=recent_activity)

@app.route('/admin/toggle-user/<int:user_id>')
@admin_required
def admin_toggle_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('UPDATE users SET is_active = NOT is_active WHERE id = %s', (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    
    flash('User status updated', 'success')
    return redirect('/admin')

@app.route('/admin/make-admin/<int:user_id>')
@admin_required
def admin_make_admin(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('INSERT INTO admin_users (user_id) VALUES (%s) ON CONFLICT DO NOTHING', (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    
    flash('User granted admin access', 'success')
    return redirect('/admin')

@app.route('/admin/demote-admin/<int:user_id>')
@admin_required
def admin_demote_admin(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('DELETE FROM admin_users WHERE user_id = %s', (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    
    flash('Admin privileges removed', 'success')
    return redirect('/admin')

@app.route('/admin/delete-user/<int:user_id>')
@admin_required
def admin_delete_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Remove from admin_users first (if exists)
        cur.execute('DELETE FROM admin_users WHERE user_id = %s', (user_id,))
        # Delete the user
        cur.execute('DELETE FROM users WHERE id = %s', (user_id,))
        conn.commit()
        flash('User deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting user: {str(e)}', 'error')
    finally:
        cur.close()
        conn.close()
    
    return redirect('/admin')

@app.route('/admin/users')
@admin_required
def admin_manage_users():
    """Redirect to main admin dashboard for user management"""
    return redirect('/admin')

@app.route('/admin/watchlists')
@admin_required
def admin_manage_watchlists():
    """Admin page to manage watchlists"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get all watchlists
    cur.execute('SELECT id, name, symbols FROM watchlists ORDER BY name')
    watchlists = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template_string(WATCHLISTS_TEMPLATE, watchlists=watchlists)

@app.route('/admin/watchlists/save', methods=['POST'])
@admin_required
def save_watchlist():
    """Save or update a watchlist"""
    name = request.form.get('name', '').strip()
    symbols = request.form.get('symbols', '').strip()
    watchlist_id = request.form.get('id')
    
    if not name or not symbols:
        flash('Name and symbols are required', 'error')
        return redirect('/admin/watchlists')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        if watchlist_id:
            # Update existing watchlist
            cur.execute(
                'UPDATE watchlists SET name = %s, symbols = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s',
                (name, symbols, watchlist_id)
            )
        else:
            # Create new watchlist
            cur.execute(
                'INSERT INTO watchlists (name, symbols, created_by) VALUES (%s, %s, %s)',
                (name, symbols, session['user_id'])
            )
        
        conn.commit()
        flash('Watchlist saved successfully', 'success')
    except Exception as e:
        flash(f'Error saving watchlist: {str(e)}', 'error')
    finally:
        cur.close()
        conn.close()
    
    return redirect('/admin/watchlists')

@app.route('/admin/watchlists/delete/<int:watchlist_id>')
@admin_required
def delete_watchlist(watchlist_id):
    """Delete a watchlist"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('DELETE FROM watchlists WHERE id = %s', (watchlist_id,))
        conn.commit()
        flash('Watchlist deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting watchlist: {str(e)}', 'error')
    finally:
        cur.close()
        conn.close()
    
    return redirect('/admin/watchlists')

@app.route('/forecast')
# @login_required  # Temporarily disabled for testing
def watchlist_forecast():
    """Watchlist forecasting page for all users"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get all watchlists for dropdown
    cur.execute('SELECT id, name FROM watchlists ORDER BY name')
    watchlists = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template_string(FORECAST_TEMPLATE, watchlists=watchlists)

@app.route('/api/forecast', methods=['POST'])
# @login_required  # Temporarily disabled for testing  
def run_forecast():
    """Run forecast for selected watchlist"""
    try:
        data = request.get_json()
        watchlist_id = data.get('watchlist_id')
        start_date = data.get('start_date', datetime.now().strftime('%Y-%m-%d'))
        
        if not watchlist_id:
            return jsonify({'error': 'Watchlist ID required'}), 400
        
        # Get watchlist symbols
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT symbols FROM watchlists WHERE id = %s', (watchlist_id,))
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if not result:
            return jsonify({'error': 'Watchlist not found'}), 404
        
        # Parse symbols from comma/space separated string
        symbols_str = result[0]
        import re
        symbols = [s.strip().upper() for s in re.split(r'[,\s]+', symbols_str) if s.strip()]
        
        # Get current stock prices and run predictions
        forecast_results = []
        
        for symbol in symbols:
            try:
                # Get current price
                ticker = yf.Ticker(symbol)
                info = ticker.info
                current_price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
                
                if current_price == 0:
                    # Try getting it from history if info doesn't have current price
                    hist = ticker.history(period='1d')
                    if not hist.empty:
                        current_price = float(hist['Close'].iloc[-1])
                
                # Get available expiration dates using yfinance (same as calculator)
                expirations = _fetch_expirations(symbol)
                start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
                
                # Filter real yfinance expiration dates to get next 4 AFTER start_date
                valid_exps = []
                for exp_str in expirations:
                    exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
                    if exp_date > start_dt:  # Only dates AFTER start_date
                        valid_exps.append(exp_str)
                
                # Sort by date to ensure proper chronological order
                valid_exps.sort()
                
                # Take first 4 valid expiration dates (real yfinance dates like Sep 19, Oct 17, Nov 21, Dec 19)
                next_four_exps = valid_exps[:4]
                
                # Calculate predictions for each expiration
                predictions = []
                for exp_date in next_four_exps:
                    try:
                        # Get options data for this expiration
                        calls, puts = _fetch_chain(symbol, exp_date)
                        
                        # Use exact same Bulls Want / Bears Want math as single calculator
                        result = _compute_results(symbol, exp_date, calls, puts)
                        
                        # Calculate Bulls Want (calls): Strike × OI weighted average
                        call_rows = [r for r in result['rows'] if r['Type'] == 'Call']
                        total_bulls_will_pay = 0
                        bulls_numerator = 0
                        
                        for call in call_rows:
                            strike = call['Strike'] or 0
                            oi = call['OI'] or 0
                            will_pay = strike * oi
                            total_bulls_will_pay += will_pay
                            bulls_numerator += strike * will_pay
                        
                        bulls_want = bulls_numerator / total_bulls_will_pay if total_bulls_will_pay > 0 else current_price
                        
                        # Calculate Bears Want (puts): Strike × OI weighted average  
                        put_rows = [r for r in result['rows'] if r['Type'] == 'Put']
                        total_bears_will_pay = 0
                        bears_numerator = 0
                        
                        for put in put_rows:
                            strike = put['Strike'] or 0
                            oi = put['OI'] or 0
                            will_pay = strike * oi
                            total_bears_will_pay += will_pay
                            bears_numerator += strike * will_pay
                        
                        bears_want = bears_numerator / total_bears_will_pay if total_bears_will_pay > 0 else current_price
                        
                        # Average Consensus = (Bulls Want + Bears Want) / 2
                        average_consensus = (bulls_want + bears_want) / 2
                        predicted_price = average_consensus
                        
                        predictions.append({
                            'expiration': exp_date,
                            'predicted_price': predicted_price,
                            'percent_change': ((predicted_price - current_price) / current_price * 100) if current_price > 0 else 0
                        })
                    except Exception as e:
                        # If we can't get options data, use current price as prediction
                        predictions.append({
                            'expiration': exp_date,
                            'predicted_price': current_price,
                            'percent_change': 0.0
                        })
                
                # Fill missing predictions if less than 4
                while len(predictions) < 4:
                    predictions.append({
                        'expiration': 'N/A',
                        'predicted_price': current_price,
                        'percent_change': 0.0
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
        return jsonify({'error': str(e)}), 500

# Static file serving
@app.route('/')
def serve_index():
    # Check if user is logged in
    user_email = session.get('user_email')
    is_logged_in = user_email is not None
    
    # Read the index.html file and modify it
    with open('index.html', 'r') as f:
        content = f.read()
    
    # Replace "Market Overview" with "Market Pulse"
    content = content.replace('Market Overview', 'Market Pulse')
    
    # Modify navigation based on login status
    if is_logged_in:
        # Show user status icon and active Tools menu
        nav_actions = f'''<div class="nav-actions">
          <div class="user-status" title="Welcome {user_email}">
            <span class="user-icon">👤</span>
          </div>
          <a href="/logout" class="btn-login">Log Out</a>
        </div>'''
        
        # Enable Tools menu with Watchlist Forecast
        tools_menu = '''<div class="nav-item dropdown">
            <a href="#">Tools</a>
            <div class="dropdown-content">
              <a href="/calculator.html">Options Calculator</a>
              <a href="/forecast">Watchlist Forecast</a>
            </div>
          </div>'''
    else:
        # Show login/signup buttons
        nav_actions = '''<div class="nav-actions">
          <a href="/login" class="btn-login">Log In</a>
          <a href="/signup" class="btn-signup">Sign Up</a>
        </div>'''
        
        # Disable Tools menu (grey out)
        tools_menu = '''<div class="nav-item dropdown disabled">
            <a href="#" style="color: #ccc; cursor: not-allowed;">Tools</a>
          </div>'''
    
    # Replace nav actions
    content = content.replace('''<div class="nav-actions">
          <a href="/login" class="btn-login">Log In</a>
          <a href="/signup" class="btn-signup">Sign Up</a>
        </div>''', nav_actions)
    
    # Replace tools menu
    content = content.replace('''<div class="nav-item dropdown">
            <a href="#">Tools</a>
            <div class="dropdown-content">
              <a href="/calculator.html">Options Calculator</a>
            </div>
          </div>''', tools_menu)
    
    return content

@app.route('/calculator.html')
# @login_required  # Temporarily disabled for testing
def serve_calculator():
    # Check if current user is admin
    is_admin = False
    if 'user_id' in session:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM admin_users WHERE user_id = %s', (session['user_id'],))
        result = cur.fetchone()
        is_admin = result[0] > 0 if result else False
        cur.close()
        conn.close()
    
    # Read the calculator HTML file
    with open('calculator.html', 'r') as f:
        content = f.read()
    
    # Replace the nav menu and actions based on admin status
    if is_admin:
        nav_menu_and_actions = '''<div class="nav-menu">
          <div class="nav-item dropdown">
            <a href="#">Tools</a>
            <div class="dropdown-content">
              <a href="/calculator.html">Options Calculator</a>
              <a href="/forecast">Watchlist Forecast</a>
            </div>
          </div>
          <div class="nav-item dropdown">
            <a href="#">Education</a>
            <div class="dropdown-content">
              <a href="/video-tutorials.html">Video Tutorials</a>
            </div>
          </div>
          <div class="nav-item dropdown">
            <a href="#">Admin</a>
            <div class="dropdown-content">
              <a href="/admin/users">Manage Users</a>
              <a href="/admin/watchlists">Manage Watchlists</a>
            </div>
          </div>
        </div>
        </div>
        <div class="nav-actions">
          <div class="user-status" title="Welcome {session.get('user_email', '')}">
            <span class="user-icon">👤</span>
          </div>
          <a href="/logout" class="btn-signup">Logout</a>
        </div>'''
    else:
        nav_menu_and_actions = '''<div class="nav-menu">
          <div class="nav-item dropdown">
            <a href="#">Tools</a>
            <div class="dropdown-content">
              <a href="/calculator.html">Options Calculator</a>
              <a href="/forecast">Watchlist Forecast</a>
            </div>
          </div>
          <div class="nav-item dropdown">
            <a href="#">Education</a>
            <div class="dropdown-content">
              <a href="/video-tutorials.html">Video Tutorials</a>
            </div>
          </div>
        </div>
        </div>
        <div class="nav-actions">
          <div class="user-status" title="Welcome {session.get('user_email', '')}">
            <span class="user-icon">👤</span>
          </div>
          <a href="/logout" class="btn-signup">Logout</a>
        </div>'''
    
    # Replace the navigation section from nav-menu to nav-actions
    import re
    content = re.sub(r'<div class="nav-menu">.*?<div class="nav-actions">.*?</div>', nav_menu_and_actions, content, flags=re.DOTALL)
    
    return content

@app.route('/video-tutorials.html')
def serve_video_tutorials():
    # Check if user is logged in
    user_email = session.get('user_email')
    is_logged_in = user_email is not None
    
    # Read the video-tutorials.html file and modify it
    with open('video-tutorials.html', 'r') as f:
        content = f.read()
    
    # Modify navigation based on login status
    if is_logged_in:
        # Show user status icon and active Tools menu
        nav_actions = f'''<div class="nav-actions">
          <div class="user-status" title="Welcome {user_email}">
            <span class="user-icon">👤</span>
          </div>
          <a href="/logout" class="btn-login">Log Out</a>
        </div>'''
        
        # Enable Tools menu with Watchlist Forecast
        tools_menu = '''<div class="nav-item dropdown">
            <a href="#">Tools</a>
            <div class="dropdown-content">
              <a href="/calculator.html">Options Calculator</a>
              <a href="/forecast">Watchlist Forecast</a>
            </div>
          </div>'''
    else:
        # Show login/signup buttons
        nav_actions = '''<div class="nav-actions">
          <a href="/login" class="btn-login">Log In</a>
          <a href="/signup" class="btn-signup">Sign Up</a>
        </div>'''
        
        # Disable Tools menu (grey out)
        tools_menu = '''<div class="nav-item dropdown disabled">
            <a href="#" style="color: #ccc; cursor: not-allowed;">Tools</a>
          </div>'''
    
    # Replace nav actions
    content = content.replace('''<div class="nav-actions">
          <a href="/login" class="btn-login">Log In</a>
          <a href="/signup" class="btn-signup">Sign Up</a>
        </div>''', nav_actions)
    
    # Replace tools menu
    content = content.replace('''<div class="nav-item dropdown">
            <a href="#">Tools</a>
            <div class="dropdown-content">
              <a href="/calculator.html">Options Calculator</a>
            </div>
          </div>''', tools_menu)
    
    return content

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

# HTML Templates
LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Selling-options.com</title>
    <link rel="stylesheet" href="/style.css">
    <link rel="icon" href="favicon.ico" type="image/x-icon">
    <link rel="icon" href="favicon-32x32.png" type="image/png" sizes="32x32">
    <link rel="icon" href="favicon-16x16.png" type="image/png" sizes="16x16">
    <style>
        .auth-container { max-width: 400px; margin: 100px auto; padding: 40px; }
        .auth-form { background: white; padding: 40px; border-radius: 20px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); }
        .auth-form h1 { text-align: center; margin-bottom: 30px; color: #1f2937; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: 600; color: #374151; }
        .form-group input { width: 100%; padding: 12px 16px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 1rem; }
        .form-group input:focus { outline: none; border-color: #1e40af; box-shadow: 0 0 0 3px rgba(30, 64, 175, 0.1); }
        .auth-btn { width: 100%; padding: 12px; background: linear-gradient(135deg, #1e40af 0%, #7c3aed 100%); color: white; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; margin-bottom: 20px; }
        .auth-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 15px rgba(30, 64, 175, 0.3); }
        .auth-link { text-align: center; color: #6b7280; }
        .auth-link a { color: #1e40af; text-decoration: none; font-weight: 600; }
        .flash-messages { margin-bottom: 20px; }
        .flash-error { background: #fee2e2; color: #dc2626; padding: 10px; border-radius: 6px; margin-bottom: 10px; }
        .flash-success { background: #d1fae5; color: #059669; padding: 10px; border-radius: 6px; margin-bottom: 10px; }
        .nav-user-login { opacity: 0.4; cursor: not-allowed; }
        .nav-user-login .user-icon { color: #9ca3af; }
    </style>
</head>
<body>
    <header class="header">
        <nav class="nav-container">
            <div class="logo">
                <img src="attached_assets/generated_images/Clean_upward_chart_icon_3aeef765.png" alt="Chart Logo" class="logo-image">
                <strong>Selling-options.com</strong>
            </div>
            <div class="nav-center">
                <div class="nav-quote">
                    <input type="text" id="navQuoteSymbol" placeholder="Enter symbol..." class="nav-quote-input">
                    <button onclick="getNavQuote()" class="nav-quote-btn">Quote</button>
                    <div id="navQuoteResult" class="nav-quote-result"></div>
                </div>
            </div>
            <div class="nav-right">
                <div class="nav-dropdown disabled">
                    <span class="nav-dropdown-label">Tools</span>
                    <div class="nav-dropdown-content">
                        <a href="/calculator.html">Options Calculator</a>
                        <a href="/forecast">Watchlist Forecast</a>
                    </div>
                </div>
                <div class="nav-dropdown">
                    <span class="nav-dropdown-label">Education</span>
                    <div class="nav-dropdown-content">
                        <a href="/video-tutorials.html">Video Tutorials</a>
                    </div>
                </div>
                <div class="nav-user-login">
                    <span class="user-icon" title="Login to access your account">👤</span>
                </div>
            </div>
        </nav>
    </header>

    <div class="auth-container">
        <div class="auth-form">
            <h1>Login</h1>
            <div class="flash-messages">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="flash-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
            </div>
            <form method="POST">
                <div class="form-group">
                    <label for="email">Email</label>
                    <input type="email" id="email" name="email" required>
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <button type="submit" class="auth-btn">Login</button>
            </form>
            <div class="auth-link">
                Don't have an account? <a href="/signup">Sign up here</a>
            </div>
        </div>
    </div>

    <script>
      // Navigation stock quote functionality
      async function getNavQuote() {
        const symbol = document.getElementById('navQuoteSymbol').value.trim().toUpperCase();
        const resultDiv = document.getElementById('navQuoteResult');
        
        if (!symbol) {
          resultDiv.innerHTML = '<div class="nav-quote-error">Enter symbol</div>';
          setTimeout(() => resultDiv.innerHTML = '', 3000);
          return;
        }
        
        resultDiv.innerHTML = '<div class="nav-quote-loading">Loading...</div>';
        
        try {
          const response = await fetch(`/api/quote?symbol=${symbol}`);
          const data = await response.json();
          
          if (data.error) {
            resultDiv.innerHTML = `<div class="nav-quote-error">Not found</div>`;
          } else {
            resultDiv.innerHTML = `
              <div class="nav-quote-success">
                ${data.symbol}: $${data.price}
              </div>
            `;
          }
          
          // Clear result after 5 seconds
          setTimeout(() => resultDiv.innerHTML = '', 5000);
        } catch (error) {
          resultDiv.innerHTML = '<div class="nav-quote-error">Error</div>';
          setTimeout(() => resultDiv.innerHTML = '', 3000);
        }
      }

      // Allow Enter key for nav quote search
      document.addEventListener('DOMContentLoaded', function() {
        const navQuoteInput = document.getElementById('navQuoteSymbol');
        if (navQuoteInput) {
          navQuoteInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
              getNavQuote();
            }
          });
        }
      });
    </script>
</body>
</html>
'''

SIGNUP_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up - Selling-options.com</title>
    <link rel="stylesheet" href="/style.css">
    <style>
        .auth-container { max-width: 400px; margin: 100px auto; padding: 40px; }
        .auth-form { background: white; padding: 40px; border-radius: 20px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); }
        .auth-form h1 { text-align: center; margin-bottom: 30px; color: #1f2937; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: 600; color: #374151; }
        .form-group input { width: 100%; padding: 12px 16px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 1rem; }
        .form-group input:focus { outline: none; border-color: #1e40af; box-shadow: 0 0 0 3px rgba(30, 64, 175, 0.1); }
        .auth-btn { width: 100%; padding: 12px; background: linear-gradient(135deg, #1e40af 0%, #7c3aed 100%); color: white; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; margin-bottom: 20px; }
        .auth-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 15px rgba(30, 64, 175, 0.3); }
        .auth-link { text-align: center; color: #6b7280; }
        .auth-link a { color: #1e40af; text-decoration: none; font-weight: 600; }
        .flash-messages { margin-bottom: 20px; }
        .flash-error { background: #fee2e2; color: #dc2626; padding: 10px; border-radius: 6px; margin-bottom: 10px; }
        .flash-success { background: #d1fae5; color: #059669; padding: 10px; border-radius: 6px; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="auth-container">
        <div class="auth-form">
            <h1>Sign Up</h1>
            <div class="flash-messages">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="flash-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
            </div>
            <form method="POST">
                <div class="form-group">
                    <label for="email">Email</label>
                    <input type="email" id="email" name="email" required>
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required minlength="6">
                </div>
                <button type="submit" class="auth-btn">Sign Up</button>
            </form>
            <div class="auth-link">
                Already have an account? <a href="/login">Login here</a>
            </div>
        </div>
    </div>
</body>
</html>
'''

ADMIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard - Selling-options.com</title>
    <link rel="stylesheet" href="/style.css">
    <style>
        .admin-container { max-width: 1200px; margin: 40px auto; padding: 20px; }
        .admin-header { text-align: center; margin-bottom: 40px; }
        .admin-header h1 { color: #1f2937; margin-bottom: 10px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 40px; }
        .stat-card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; }
        .stat-number { font-size: 2rem; font-weight: bold; color: #1e40af; }
        .users-table { background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 30px; }
        .users-table table { width: 100%; border-collapse: collapse; }
        .users-table th { background: #f8fafc; padding: 15px; text-align: left; font-weight: 600; color: #374151; }
        .users-table td { padding: 15px; border-bottom: 1px solid #f3f4f6; }
        .status-active { color: #059669; font-weight: 600; }
        .status-inactive { color: #dc2626; font-weight: 600; }
        .admin-badge { background: #1e40af; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; }
        .action-btn { padding: 5px 10px; margin: 2px; border: none; border-radius: 4px; cursor: pointer; font-size: 0.8rem; text-decoration: none; display: inline-block; }
        .btn-toggle { background: #f59e0b; color: white; }
        .btn-admin { background: #1e40af; color: white; }
        .btn-demote { background: #dc2626; color: white; }
        .btn-delete { background: #991b1b; color: white; }
        .flash-messages { margin-bottom: 20px; }
        .flash-success { background: #d1fae5; color: #059669; padding: 10px; border-radius: 6px; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="admin-container">
        <div class="admin-header">
            <h1>Admin Dashboard</h1>
            <p>Manage users and monitor site activity</p>
        </div>
        
        <div class="flash-messages">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{{ users|length }}</div>
                <div>Total Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ users|selectattr("5")|list|length }}</div>
                <div>Active Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ recent_activity|length }}</div>
                <div>Active This Month</div>
            </div>
        </div>

        <div class="users-table">
            <table>
                <thead>
                    <tr>
                        <th>Email</th>
                        <th>Joined</th>
                        <th>Last Login</th>
                        <th>Logins</th>
                        <th>Status</th>
                        <th>Role</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for user in users %}
                    <tr>
                        <td>{{ user[1] }}</td>
                        <td>{{ user[2].strftime('%Y-%m-%d') if user[2] else 'N/A' }}</td>
                        <td>{{ user[3].strftime('%Y-%m-%d %H:%M') if user[3] else 'Never' }}</td>
                        <td>{{ user[4] or 0 }}</td>
                        <td>
                            {% if user[5] %}
                                <span class="status-active">Active</span>
                            {% else %}
                                <span class="status-inactive">Inactive</span>
                            {% endif %}
                        </td>
                        <td>
                            {% if user[6] %}
                                <span class="admin-badge">Admin</span>
                            {% else %}
                                User
                            {% endif %}
                        </td>
                        <td>
                            <a href="/admin/toggle-user/{{ user[0] }}" class="action-btn btn-toggle">
                                {{ 'Deactivate' if user[5] else 'Activate' }}
                            </a>
                            {% if not user[6] %}
                                <a href="/admin/make-admin/{{ user[0] }}" class="action-btn btn-admin">Make Admin</a>
                            {% else %}
                                <a href="/admin/demote-admin/{{ user[0] }}" class="action-btn btn-demote">Demote</a>
                            {% endif %}
                            <a href="/admin/delete-user/{{ user[0] }}" class="action-btn btn-delete" onclick="return confirm('Are you sure you want to delete this user? This action cannot be undone.')">Delete</a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div style="text-align: center; margin-top: 30px;">
            <a href="/" class="action-btn btn-admin">Back</a>
            <a href="/logout" class="action-btn btn-toggle">Logout</a>
        </div>
    </div>
</body>
</html>
'''

WATCHLISTS_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Manage Watchlists - Selling-options.com</title>
    <link rel="stylesheet" href="/style.css">
    <style>
        .admin-container { max-width: 1000px; margin: 40px auto; padding: 20px; }
        .admin-header { text-align: center; margin-bottom: 40px; }
        .admin-header h1 { color: #1f2937; margin-bottom: 10px; }
        .watchlist-form { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 30px; }
        .form-row { display: grid; grid-template-columns: 1fr 2fr auto; gap: 15px; align-items: end; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: 600; color: #374151; }
        .form-group input, .form-group textarea { width: 100%; padding: 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 1rem; }
        .form-group input:focus, .form-group textarea:focus { outline: none; border-color: #1e40af; box-shadow: 0 0 0 3px rgba(30, 64, 175, 0.1); }
        .watchlist-btn { padding: 12px 20px; background: linear-gradient(135deg, #1e40af 0%, #7c3aed 100%); color: white; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; }
        .watchlist-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 15px rgba(30, 64, 175, 0.3); }
        .watchlists-table { background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .watchlists-table table { width: 100%; border-collapse: collapse; }
        .watchlists-table th { background: #f8fafc; padding: 15px; text-align: left; font-weight: 600; color: #374151; }
        .watchlists-table td { padding: 15px; border-bottom: 1px solid #f3f4f6; }
        .action-btn { padding: 5px 10px; margin: 2px; border: none; border-radius: 4px; cursor: pointer; font-size: 0.8rem; text-decoration: none; display: inline-block; }
        .btn-delete { background: #dc2626; color: white; }
        .btn-edit { background: #f59e0b; color: white; }
        .btn-back { background: #1e40af; color: white; padding: 10px 20px; margin-top: 20px; }
        .flash-messages { margin-bottom: 20px; }
        .flash-success { background: #d1fae5; color: #059669; padding: 10px; border-radius: 6px; margin-bottom: 10px; }
        .flash-error { background: #fee2e2; color: #dc2626; padding: 10px; border-radius: 6px; margin-bottom: 10px; }
        .symbols-display { font-family: monospace; font-size: 0.9rem; }
    </style>
</head>
<body>
    <div class="admin-container">
        <div class="admin-header">
            <h1>Manage Watchlists</h1>
            <p>Create and manage stock symbol watchlists</p>
        </div>
        
        <div class="flash-messages">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
        </div>

        <div class="watchlist-form">
            <h2>Create New Watchlist</h2>
            <form method="POST" action="/admin/watchlists/save">
                <div class="form-group">
                    <label for="name">Name</label>
                    <input type="text" id="name" name="name" placeholder="My List" required>
                </div>
                <div class="form-group">
                    <label for="symbols">Symbols (comma or space separated)</label>
                    <textarea id="symbols" name="symbols" rows="3" placeholder="AAPL, MSFT, NVDA" required></textarea>
                </div>
                <button type="submit" class="watchlist-btn">Save Watchlist</button>
            </form>
        </div>

        {% if watchlists %}
        <div class="watchlists-table">
            <h2 style="padding: 20px; margin: 0; background: #f8fafc; font-size: 1.2rem; color: #374151;">Existing Watchlists</h2>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Symbols</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for watchlist in watchlists %}
                    <tr>
                        <td>{{ watchlist[1] }}</td>
                        <td class="symbols-display">{{ watchlist[2] }}</td>
                        <td>
                            <a href="/admin/watchlists/delete/{{ watchlist[0] }}" 
                               class="action-btn btn-delete"
                               onclick="return confirm('Are you sure you want to delete this watchlist?')">Delete</a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}

        <div style="text-align: center;">
            <a href="/admin" class="action-btn btn-back">Back to Admin</a>
        </div>
    </div>
</body>
</html>
'''

FORECAST_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Watchlist Forecast - Selling-options.com</title>
    <link rel="stylesheet" href="/style.css">
    <style>
        .forecast-container { max-width: 1400px; margin: 40px auto; padding: 20px; }
        .forecast-header { text-align: center; margin-bottom: 40px; }
        .forecast-header h1 { color: #1f2937; margin-bottom: 10px; }
        .forecast-controls { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 30px; }
        .controls-row { display: grid; grid-template-columns: 1fr 1fr auto auto; gap: 20px; align-items: end; }
        .form-group { margin-bottom: 0; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: 600; color: #374151; }
        .form-group select, .form-group input { width: 100%; padding: 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 1rem; }
        .form-group select:focus, .form-group input:focus { outline: none; border-color: #1e40af; box-shadow: 0 0 0 3px rgba(30, 64, 175, 0.1); }
        .forecast-btn { padding: 12px 24px; background: linear-gradient(135deg, #059669 0%, #047857 100%); color: white; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; }
        .forecast-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 15px rgba(5, 150, 105, 0.3); }
        .forecast-btn:disabled { background: #9ca3af; cursor: not-allowed; transform: none; box-shadow: none; }
        .manage-btn { padding: 12px 20px; background: linear-gradient(135deg, #1e40af 0%, #7c3aed 100%); color: white; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; }
        .manage-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 15px rgba(30, 64, 175, 0.3); }
        .results-container { background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); display: none; }
        .results-table { width: 100%; border-collapse: collapse; }
        .results-table th { background: #f8fafc; padding: 15px 12px; text-align: left; font-weight: 600; color: #374151; font-size: 0.9rem; }
        .results-table td { padding: 12px; border-bottom: 1px solid #f3f4f6; font-size: 0.9rem; }
        .symbol-cell { font-weight: 600; color: #1e40af; }
        .price-cell { font-family: monospace; }
        .positive { color: #059669; }
        .negative { color: #dc2626; }
        .neutral { color: #6b7280; }
        .loading { text-align: center; padding: 40px; color: #6b7280; }
        .error-message { background: #fee2e2; color: #dc2626; padding: 15px; border-radius: 8px; margin: 20px 0; }
        .forecast-ready { background: #d1fae5; color: #059669; padding: 10px; border-radius: 6px; margin: 10px 0; text-align: center; font-weight: 600; }
        .back-btn { background: #6b7280; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; display: inline-block; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="forecast-container">
        <div class="forecast-header">
            <h1>Watchlist Forecast</h1>
            <p>Analyze options sentiment across entire watchlists for next 4 expiration dates</p>
        </div>
        
        <div class="forecast-controls">
            <div class="controls-row">
                <div class="form-group">
                    <label for="watchlist">Watchlist</label>
                    <select id="watchlist" required>
                        <option value="">Select a watchlist...</option>
                        {% for watchlist in watchlists %}
                        <option value="{{ watchlist[0] }}">{{ watchlist[1] }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-group">
                    <label for="startDate">Starting Expiration (YYYY-MM-DD)</label>
                    <input type="date" id="startDate">
                </div>
                <div>
                    <button id="runForecast" class="forecast-btn" onclick="runForecast()">Run Forecast</button>
                </div>
            </div>
            <div id="forecastStatus"></div>
        </div>

        <div id="resultsContainer" class="results-container">
            <div class="loading" id="loadingIndicator">
                Analyzing options data across watchlist...
            </div>
            <div id="forecastResults" style="display: none;"></div>
        </div>

        <div style="text-align: center;">
            <a href="/" class="back-btn">Back</a>
        </div>
    </div>

    <script>
        // Set today's date as default
        document.getElementById('startDate').value = new Date().toISOString().split('T')[0];

        async function runForecast() {
            const watchlistId = document.getElementById('watchlist').value;
            const startDate = document.getElementById('startDate').value;
            
            if (!watchlistId) {
                alert('Please select a watchlist');
                return;
            }
            
            const btn = document.getElementById('runForecast');
            const status = document.getElementById('forecastStatus');
            const container = document.getElementById('resultsContainer');
            const loading = document.getElementById('loadingIndicator');
            const results = document.getElementById('forecastResults');
            
            // Show loading state
            btn.disabled = true;
            btn.textContent = 'Running...';
            status.innerHTML = '<div class="forecast-ready">Fetching options data and calculating predictions...</div>';
            container.style.display = 'block';
            loading.style.display = 'block';
            results.style.display = 'none';
            
            try {
                const response = await fetch('/api/forecast', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        watchlist_id: watchlistId,
                        start_date: startDate
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    displayResults(data.results);
                    status.innerHTML = '<div class="forecast-ready">✓ Forecast ready for ' + data.results.length + ' symbols</div>';
                } else {
                    throw new Error(data.error || 'Forecast failed');
                }
            } catch (error) {
                status.innerHTML = '<div class="error-message">Error: ' + error.message + '</div>';
                container.style.display = 'none';
            } finally {
                btn.disabled = false;
                btn.textContent = 'Run Forecast';
                loading.style.display = 'none';
            }
        }
        
        function displayResults(data) {
            const results = document.getElementById('forecastResults');
            
            if (!data || data.length === 0) {
                results.innerHTML = '<div class="error-message">No forecast data available</div>';
                results.style.display = 'block';
                return;
            }
            
            // Build the results table
            let html = '<table class="results-table"><thead><tr>';
            html += '<th>Symbol</th>';
            html += '<th>Current Price</th>';
            html += '<th>Expiration</th>';
            html += '<th>Predicted</th>';
            html += '<th>% Δ</th>';
            html += '<th>Expiration+1</th>';
            html += '<th>Predicted</th>';
            html += '<th>% Δ</th>';
            html += '<th>Expiration+2</th>';
            html += '<th>Predicted</th>';
            html += '<th>% Δ</th>';
            html += '<th>Expiration+3</th>';
            html += '<th>Predicted</th>';
            html += '<th>% Δ</th>';
            html += '</tr></thead><tbody>';
            
            data.forEach(stock => {
                html += '<tr>';
                html += '<td class="symbol-cell">' + stock.symbol + '</td>';
                html += '<td class="price-cell">$' + (stock.current_price || 0).toFixed(2) + '</td>';
                
                // Add 4 expiration columns
                for (let i = 0; i < 4; i++) {
                    const pred = stock.predictions[i] || {};
                    const expDate = pred.expiration ? pred.expiration.substring(5, 10) : 'N/A';
                    const predPrice = pred.predicted_price || 0;
                    const pctChange = pred.percent_change || 0;
                    
                    html += '<td>' + expDate + '</td>';
                    html += '<td class="price-cell">$' + predPrice.toFixed(2) + '</td>';
                    
                    const changeClass = pctChange > 0.01 ? 'positive' : pctChange < -0.01 ? 'negative' : 'neutral';
                    html += '<td class="' + changeClass + '">' + pctChange.toFixed(2) + '%</td>';
                }
                
                html += '</tr>';
            });
            
            html += '</tbody></table>';
            results.innerHTML = html;
            results.style.display = 'block';
        }
    </script>
</body>
</html>
'''

# Database initialization functions
def create_tables():
    """Create the required database tables"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create users table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create admin_users table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create watchlist table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            symbol VARCHAR(10) NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, symbol)
        )
    ''')
    
    conn.commit()
    cur.close()
    conn.close()

def create_admin_user(email, password):
    """Create an admin user"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if user already exists
    cur.execute('SELECT id FROM users WHERE email = %s', (email,))
    existing_user = cur.fetchone()
    
    if existing_user:
        user_id = existing_user[0]
        print(f'User {email} already exists')
    else:
        # Create new user
        password_hash = hash_password(password)
        cur.execute('INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id', 
                   (email, password_hash))
        user_id = cur.fetchone()[0]
        print(f'Created user {email}')
    
    # Make user admin if not already
    cur.execute('SELECT 1 FROM admin_users WHERE user_id = %s', (user_id,))
    if not cur.fetchone():
        cur.execute('INSERT INTO admin_users (user_id) VALUES (%s)', (user_id,))
        print(f'Granted admin privileges to {email}')
    else:
        print(f'User {email} already has admin privileges')
    
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)