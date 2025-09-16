# Selling-Options.com - Professional Options Trading Platform

## Overview

Selling-Options.com is a professional Flask-based web application for options trading analysis, inspired by TipRanks.com. The platform provides comprehensive tools for options traders including sentiment analysis, options chain evaluation, and real-time market insights. The primary purpose is to help options traders make data-driven decisions by analyzing options chains, calculating probabilities (Bulls Want/Bears Want), and providing professional-grade market data with a focus on end-of-day reliability over real-time snapshots.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture
- **Flask 2.3.3** with modular blueprint structure for clean separation of concerns
- **Python 3.11** runtime with organized service layer for business logic
- **Blueprint-based routing** with dedicated modules for auth, calculator, forecast, admin, and API endpoints
- **Session management** using Flask-Session with filesystem storage for user state
- **Defensive programming** patterns with extensive error handling for financial data edge cases

### Frontend Architecture
- **Server-side rendering** with Jinja2 templating and template inheritance via base.html
- **Vanilla JavaScript** for interactive components without heavy framework dependencies
- **TipRanks-inspired responsive design** using CSS Grid and Flexbox with mobile-first approach
- **Centralized navigation system** with dynamic admin controls and authentication-aware UI states
- **Component-based JavaScript** with modular calculator classes for complex financial calculations

### Data Processing & Market Data
- **Primary data source**: Polygon.io API for comprehensive market data (stocks, options chains, quotes)
- **Market awareness system** distinguishing between live trading hours and end-of-day data modes
- **Pandas 2.0.3** for financial data analysis and manipulation with NumPy 1.26.4 for mathematical operations
- **Rate limiting and caching** strategies for API efficiency with session-based HTTP connections
- **Fallback data strategies** prioritizing data reliability over real-time updates

### Authentication & Security
- **bcrypt password hashing** with secure session management
- **Role-based access control** with admin_users table for privilege escalation
- **Decorator-based protection** for routes requiring authentication or admin privileges
- **Session-based authentication** with configurable expiration and security settings

### Database Design
- **PostgreSQL 16** as primary database with psycopg2-binary adapter
- **User management schema** with users, admin_users, and user_sessions tables
- **Watchlist functionality** for portfolio tracking and bulk analysis
- **Foreign key relationships** maintaining data integrity across user interactions

### API Architecture
- **RESTful endpoint design** following /api/ pattern with JSON responses
- **Market-aware data serving** switching between live and EOD modes based on trading hours
- **Symbol sanitization** and validation for secure ticker symbol processing
- **Standardized error responses** with consistent JSON structure across all endpoints

### Key Design Patterns
- **Separation of concerns** with clear boundaries between data fetching, processing, and presentation layers
- **Service layer architecture** isolating business logic from route handlers
- **Defensive programming** with safe type conversion and mathematical validation for financial calculations
- **Template inheritance** providing consistent navigation and styling across all pages
- **Market clock integration** ensuring data consistency based on actual trading session status

## External Dependencies

### Core Market Data
- **Polygon.io API** - Primary real-time and historical market data provider for stocks and options
- **Polygon API Client** - Python wrapper for streamlined API integration with rate limiting support

### Database & Infrastructure
- **PostgreSQL 16** - Primary relational database for user management and application state
- **Gunicorn 21.2.0** - Production WSGI server for Flask application deployment
- **Docker** - Containerization for consistent deployment environments

### Python Libraries
- **Flask ecosystem**: Flask-Session for session management, Werkzeug for WSGI utilities
- **Data processing**: Pandas for financial analysis, NumPy for mathematical operations
- **HTTP handling**: Requests library for external API communication with session management
- **Security**: bcrypt for password hashing and user authentication

### Development & Deployment
- **Replit** - Development environment and hosting platform
- **GitHub** - Version control and code collaboration
- **Environment variables** for API keys and configuration management (POLYGON_API_KEY, database credentials)