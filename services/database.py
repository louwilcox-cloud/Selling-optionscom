"""Database service for Selling-Options.com"""
import os
import psycopg2
from functools import wraps

def get_db_connection():
    """Get PostgreSQL database connection"""
    try:
        conn = psycopg2.connect(
            host=os.getenv('PGHOST', 'localhost'),
            database=os.getenv('PGDATABASE', 'options_db'),
            user=os.getenv('PGUSER', 'postgres'),
            password=os.getenv('PGPASSWORD', 'password'),
            port=os.getenv('PGPORT', '5432')
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def init_database():
    """Initialize database tables if they don't exist"""
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        cur = conn.cursor()
        
        # Create users table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active BOOLEAN DEFAULT TRUE
            )
        ''')
        
        # Create watchlists table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS watchlists (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                name VARCHAR(100) NOT NULL,
                symbols TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Database initialization error: {e}")
        if conn:
            conn.close()
        return False

def require_db(f):
    """Decorator to ensure database connection is available"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        conn = get_db_connection()
        if not conn:
            return {"error": "Database connection failed"}, 500
        try:
            return f(conn, *args, **kwargs)
        finally:
            conn.close()
    return decorated_function