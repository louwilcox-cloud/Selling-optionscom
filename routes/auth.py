"""Authentication routes for Selling-Options.com"""
import bcrypt
from flask import Blueprint, request, session, redirect, url_for, render_template_string, flash
from services.database import get_db_connection

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """User registration"""
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Hash password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection error', 'error')
            return redirect(url_for('auth.signup'))
        
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                (username, email, password_hash)
            )
            conn.commit()
            cur.close()
            conn.close()
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            conn.close()
            flash(f'Registration failed: {str(e)}', 'error')
            return redirect(url_for('auth.signup'))
    
    # GET request - show signup form
    signup_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sign Up - Selling-options.com</title>
        <link rel="stylesheet" href="/static/style.css">
    </head>
    <body>
        <div class="auth-container">
            <h1>Create Account</h1>
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="alert alert-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            <form method="POST">
                <div class="form-group">
                    <label>Username:</label>
                    <input type="text" name="username" required>
                </div>
                <div class="form-group">
                    <label>Email:</label>
                    <input type="email" name="email" required>
                </div>
                <div class="form-group">
                    <label>Password:</label>
                    <input type="password" name="password" required>
                </div>
                <button type="submit">Sign Up</button>
            </form>
            <p><a href="{{ url_for('auth.login') }}">Already have an account? Login</a></p>
        </div>
    </body>
    </html>
    '''
    return render_template_string(signup_html)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection error', 'error')
            return redirect(url_for('auth.login'))
        
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, password_hash FROM users WHERE username = %s AND active = true", (username,))
            user = cur.fetchone()
            cur.close()
            conn.close()
            
            if user and bcrypt.checkpw(password.encode('utf-8'), user[1].encode('utf-8')):
                session['user_id'] = user[0]
                session['username'] = username
                return redirect(url_for('main.index'))
            else:
                flash('Invalid username or password', 'error')
                
        except Exception as e:
            conn.close()
            flash(f'Login failed: {str(e)}', 'error')
    
    # GET request - show login form
    login_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - Selling-options.com</title>
        <link rel="stylesheet" href="/static/style.css">
    </head>
    <body>
        <div class="auth-container">
            <h1>Login</h1>
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="alert alert-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            <form method="POST">
                <div class="form-group">
                    <label>Username:</label>
                    <input type="text" name="username" required>
                </div>
                <div class="form-group">
                    <label>Password:</label>
                    <input type="password" name="password" required>
                </div>
                <button type="submit">Login</button>
            </form>
            <p><a href="{{ url_for('auth.signup') }}">Don't have an account? Sign up</a></p>
        </div>
    </body>
    </html>
    '''
    return render_template_string(login_html)

@auth_bp.route('/logout')
def logout():
    """User logout"""
    session.clear()
    return redirect(url_for('main.index'))