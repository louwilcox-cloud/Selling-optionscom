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
        return redirect('/calculator.html')
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect('/')

@app.route('/admin')
@admin_required
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

# Static file serving
@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/calculator.html')
@login_required
def serve_calculator():
    return send_from_directory('.', 'calculator.html')

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
                            {% endif %}
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)