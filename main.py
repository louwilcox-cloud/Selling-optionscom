#!/usr/bin/env python3
"""
Selling-Options.com - Professional Options Trading Platform
Refactored Flask application with proper modular structure
"""

import os
from flask import Flask, session
from flask_session import Session

# Import blueprints
from routes.home import main_bp
from routes.api import api_bp
from routes.auth import auth_bp
from routes.calculator import calculator_bp
from routes.forecast import forecast_bp
from routes.admin import admin_bp

# Import services
from services.database import init_database

def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-super-secret-key-change-this-in-production')
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_FILE_DIR'] = './flask_session'
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_USE_SIGNER'] = True
    
    # Initialize Flask-Session
    Session(app)
    
    # Initialize database
    init_database()
    
    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(calculator_bp)
    app.register_blueprint(forecast_bp)
    app.register_blueprint(admin_bp)
    
    return app

def main():
    """Main entry point"""
    app = create_app()
    
    # Get configuration from environment
    host = os.getenv('APP_HOST', '0.0.0.0')
    port = int(os.getenv('APP_PORT', 5000))
    debug = os.getenv('APP_DEBUG', 'false').lower() == 'true'
    
    print(f"🚀 Starting Selling-Options.com on {host}:{port}")
    print(f"📊 Polygon API: {'✓ Configured' if os.getenv('POLYGON_API_KEY') else '❌ Missing'}")
    print(f"🗄️  Database: {'✓ Available' if os.getenv('PGHOST') else '❌ Not configured'}")
    
    app.run(host=host, port=port, debug=debug)

if __name__ == '__main__':
    main()