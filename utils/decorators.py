"""Utility decorators for Selling-Options.com"""
from functools import wraps
from flask import session, redirect, url_for, request, jsonify

def login_required(f):
    """Decorator to require user login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('auth.login'))
        
        # Check if user is admin (you might want to add this to user table)
        if session.get('username') != 'admin':  # Simplified check
            if request.is_json:
                return jsonify({'error': 'Admin privileges required'}), 403
            return redirect(url_for('main.index'))
        
        return f(*args, **kwargs)
    return decorated_function

def retry_with_backoff(max_retries=3, base_delay=1):
    """Decorator for retrying functions with exponential backoff"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            import time
            
            for attempt in range(max_retries):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:  # Last attempt
                        raise e
                    
                    delay = base_delay * (2 ** attempt)
                    print(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
            
            return f(*args, **kwargs)  # Final attempt
        return wrapper
    return decorator