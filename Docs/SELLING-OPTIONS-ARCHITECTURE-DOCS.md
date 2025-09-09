# Selling-Options.com - Complete Architecture Documentation

## Overview

**Selling-Options.com** is a professional Flask-based web application for options trading analysis, inspired by TipRanks.com. The system provides comprehensive tools for options traders including sentiment analysis, options calculators, risk assessment, watchlist forecasting, and real-time market data visualization.

**Primary Purpose**: Help options traders make data-driven decisions by analyzing options chains, calculating probabilities, and providing real-time market insights with professional-grade tools.

---

## Technology Stack

### **Core Framework**
- **Flask 2.3.3**: Python web framework with modular blueprint architecture
- **Python 3.11**: Runtime environment with slim Docker image
- **PostgreSQL 16**: Primary database for user management and watchlists
- **Gunicorn 21.2.0**: Production WSGI server

### **External APIs & Services**
- **Polygon.io API**: Primary real-time market data provider
- **Polygon API Client**: Python wrapper for options chains and quotes
- **Requests**: HTTP library for API calls with session management

### **Data Processing**
- **Pandas 2.0.3**: Financial data analysis and manipulation
- **NumPy 1.26.4**: Mathematical operations (pinned for pandas compatibility)
- **bcrypt 4.0.1**: Password hashing and authentication

### **Session Management**
- **Flask-Session 0.6.0**: Filesystem-based session storage
- **psycopg2-binary 2.9.7**: PostgreSQL database adapter

### **Infrastructure & Deployment**
- **Docker**: Containerization with multi-service compose setup
- **Caddy 2**: Reverse proxy with automatic HTTPS
- **Replit**: Development environment
- **GitHub**: Version control and collaboration

### **Frontend Technologies**
- **Vanilla JavaScript**: Interactive components without heavy frameworks
- **Custom CSS**: TipRanks-inspired responsive design
- **Jinja2**: Server-side templating with Flask

---

## Project Structure

```
selling-options.com/
├── main.py                          # Main application entry point
├── requirements.txt                 # Python dependencies
├── Dockerfile                       # Container build configuration
├── docker-compose.yml              # Multi-service orchestration
├── Caddyfile                       # Reverse proxy configuration
├── lab-deploy.sh                   # Deployment script for NAS
├── replit.md                       # Project documentation & preferences
│
├── routes/                         # Flask Blueprint modules
│   ├── __init__.py
│   ├── home.py                     # Homepage and static pages
│   ├── api.py                      # REST API endpoints
│   ├── auth.py                     # Authentication system
│   ├── calculator.py               # Options calculator tools
│   ├── forecast.py                 # Watchlist analysis
│   └── admin.py                    # Admin panel functionality
│
├── services/                       # Business logic layer
│   ├── __init__.py
│   ├── database.py                 # PostgreSQL connection & schema
│   └── polygon_service.py          # Polygon.io API integration
│
├── templates/                      # Jinja2 HTML templates
│   ├── base.html                   # Master template with navigation
│   ├── index.html                  # Market Pulse homepage
│   ├── calculator.html             # Options calculator interface
│   ├── forecast.html               # Watchlist forecast tool
│   ├── video-tutorials.html        # Interactive learning system
│   ├── login.html                  # User authentication
│   ├── signup.html                 # User registration
│   ├── admin_panel.html            # User management
│   └── manage_watchlists.html      # Watchlist administration
│
├── static/                         # Frontend assets
│   ├── style.css                   # Main stylesheet (TipRanks-inspired)
│   ├── nav.js                      # Navigation & quote functionality
│   ├── calculator.js               # Options calculator logic
│   ├── favicon.ico                 # Site favicons
│   ├── favicon-16x16.png
│   ├── favicon-32x32.png
│   └── attached_assets/
│       └── generated_images/
│           └── Clean_financial_chart_logo_a5295a8c.png
│
├── utils/                          # Helper utilities
│   ├── __init__.py
│   └── decorators.py               # Retry logic and error handling
│
└── flask_session/                  # Server-side session storage
    └── [session files]
```

---

## Core Architecture

### **Application Factory Pattern**
The application uses Flask's application factory pattern in `main.py`:

```python
def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback-key')
    app.config['SESSION_TYPE'] = 'filesystem'
    
    # Initialize services
    Session(app)
    init_database()
    
    # Register all blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    # ... other blueprints
    
    return app
```

### **Blueprint Modular Design**
Each major feature is isolated into its own blueprint:

1. **`routes/home.py`** - Static pages and homepage
2. **`routes/api.py`** - REST API endpoints
3. **`routes/auth.py`** - User authentication system
4. **`routes/calculator.py`** - Options calculation tools
5. **`routes/forecast.py`** - Watchlist analysis tools
6. **`routes/admin.py`** - Administrative functions

### **Service Layer Architecture**
Business logic is separated into services:

- **`services/database.py`** - Database connections and schema
- **`services/polygon_service.py`** - External API integration
- **`utils/decorators.py`** - Cross-cutting concerns (retry logic)

---

## Environment Configuration

### **Required Environment Variables**

```bash
# Database Configuration (Provided by Replit)
PGHOST=localhost                    # PostgreSQL host
PGDATABASE=options_db              # Database name
PGUSER=postgres                    # Database user
PGPASSWORD=password                # Database password
PGPORT=5432                        # Database port
DATABASE_URL=postgresql://...      # Full connection string

# API Keys
POLYGON_API_KEY=SgahyvybcxIY8IG9vPM9QKYkF9mnbJGi  # Polygon.io API key

# Application Configuration
SECRET_KEY=your-super-secret-key   # Flask session security
APP_HOST=0.0.0.0                   # Bind address
APP_PORT=5000                      # Application port
APP_DEBUG=false                    # Debug mode (false for production)
FLASK_ENV=production               # Flask environment
```

### **Session Storage**
- **Type**: Filesystem-based sessions
- **Location**: `./flask_session/` directory
- **Security**: Signed sessions with SECRET_KEY
- **Persistence**: Survives container restarts via volume mount

---

## Database Schema

### **PostgreSQL Database Design**

```sql
-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    active BOOLEAN DEFAULT TRUE
);

-- Watchlists table
CREATE TABLE watchlists (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name VARCHAR(100) NOT NULL,
    symbols TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### **Database Service (`services/database.py`)**
- **Connection Management**: Handles PostgreSQL connections with environment variables
- **Schema Initialization**: Automatically creates tables on startup
- **Error Handling**: Graceful fallbacks for connection failures

---

## API Integration Layer

### **Polygon.io Service (`services/polygon_service.py`)**

**Key Functions:**
- **`get_market_phase()`** - Determines market status (open/closed/afterhours/pre)
- **`quote_delayed()`** - Retrieves stock quotes with multiple fallbacks
- **`get_stock_quote()`** - Comprehensive quote data with error handling
- **`get_options_expirations()`** - Available options expiration dates
- **`get_options_chain()`** - Complete options chain data for analysis

**Features:**
- **Rate Limiting**: Built-in request throttling
- **Caching**: Market status cached for performance
- **Fallback Logic**: Multiple data sources for reliability
- **Error Handling**: Graceful degradation when API fails

---

## Frontend Architecture

### **Template Inheritance System**
- **Master Template**: `templates/base.html` contains navigation and layout
- **Child Templates**: All pages extend base template for consistency
- **Centralized Navigation**: Single source of truth for site navigation

### **Navigation System (`templates/base.html`)**
```html
<header class="header">
  <nav class="nav-container">
    <div class="logo">...</div>
    <div class="nav-center">
      <!-- Live quote lookup -->
      <input id="navQuoteSymbol" placeholder="Enter symbol...">
    </div>
    <div class="nav-right">
      <!-- Tools dropdown (authenticated users) -->
      <!-- Education dropdown -->
      <!-- Admin dropdown (admin users only) -->
      <!-- Auth section (login/logout) -->
    </div>
  </nav>
</header>
```

### **Interactive Components**
- **Live Quote Widget**: Real-time symbol lookup in navigation
- **Options Calculator**: Dynamic calculation interface
- **Video Tutorial System**: Interactive learning path with dynamic video loading
- **Watchlist Forecast**: Real-time analysis tools

---

## Page-by-Page Breakdown

### **1. Homepage (`/`) - Market Pulse Dashboard**
- **Template**: `templates/index.html`
- **Route**: `routes/home.py:index()`
- **Features**: Live market data, sentiment indicators, quick access tools
- **APIs Used**: `/api/market-data`, `/api/auth-status`

### **2. Options Calculator (`/calculator`)**
- **Template**: `templates/calculator.html`
- **Route**: `routes/calculator.py:calculator()`
- **JavaScript**: `static/calculator.js`
- **Features**: Real-time options pricing, Greeks calculation, profit/loss analysis
- **APIs Used**: `/api/quote`, `/api/get_options_data`

### **3. Watchlist Forecast (`/forecast`)**
- **Template**: `templates/forecast.html`
- **Route**: `routes/forecast.py:forecast()`
- **Features**: Multi-symbol sentiment analysis, Bulls Want/Bears Want calculations
- **APIs Used**: `/api/forecast`, user authentication required

### **4. Video Tutorials (`/video-tutorials`)**
- **Template**: `templates/video-tutorials.html`
- **Route**: `routes/home.py:video_tutorials()`
- **Features**: Interactive learning path, dynamic video loading, progress tracking
- **Mapping**: Foundation→Fundamentals, Strategy→Wheel, Weekly Income→Passive Income

### **5. Authentication System**
- **Login**: `templates/login.html` via `routes/auth.py:login()`
- **Signup**: `templates/signup.html` via `routes/auth.py:signup()`
- **Features**: bcrypt password hashing, session management, role-based access

### **6. Admin Panel** (Admin Users Only)
- **User Management**: `templates/admin_panel.html`
- **Watchlist Management**: `templates/manage_watchlists.html`
- **Route**: `routes/admin.py`
- **Security**: IP-restricted in Caddyfile, session-based authentication

---

## API Endpoints

### **Public APIs**
```
GET  /api/health           # Health check for monitoring
GET  /api/quote           # Stock quote lookup
GET  /api/market-data     # Dashboard market data
GET  /api/auth-status     # Current user authentication status
```

### **Authenticated APIs**
```
GET  /api/get_options_data  # Options chains and expirations
POST /api/forecast          # Watchlist sentiment analysis
```

### **Admin APIs**
```
POST /api/admin/*          # Administrative functions
```

---

## Docker Infrastructure

### **Multi-Container Setup (`docker-compose.yml`)**

```yaml
services:
  # Flask Application
  selling-options-app:
    build: .
    expose: ["5000"]
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/options_db
    depends_on: [db]
    restart: unless-stopped

  # PostgreSQL Database
  db:
    image: postgres:16
    environment:
      - POSTGRES_DB=options_db
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  # Caddy Reverse Proxy
  caddy:
    image: caddy:2-alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
    depends_on: [selling-options-app]
    restart: unless-stopped
```

### **Dockerfile Configuration**
- **Base Image**: `python:3.11-slim`
- **Dependencies**: PostgreSQL client, GCC for compiled packages
- **Security**: Non-root user, minimal attack surface
- **Performance**: Multi-stage build with dependency caching

---

## Deployment & DevOps

### **Lab Deployment (`lab-deploy.sh`)**
Automated deployment script for NAS/lab environments:

```bash
#!/bin/bash
docker-compose down              # Stop existing services
docker-compose build --no-cache  # Fresh build
docker-compose up -d             # Start in background
# Health checks and verification
```

### **Caddy Reverse Proxy (`Caddyfile`)**
- **Security Headers**: XSS protection, content type sniffing prevention
- **Admin Protection**: IP allowlist for `/admin*` routes
- **Compression**: gzip/zstd for performance
- **SSL**: Ready for HTTPS (currently HTTP for lab)

### **Health Monitoring**
- **Endpoint**: `GET /api/health`
- **Checks**: Database connectivity, API availability, uptime
- **Integration**: Ready for monitoring systems (Prometheus, etc.)

---

## Security Features

### **Authentication & Authorization**
- **Password Security**: bcrypt hashing with salt
- **Session Management**: Server-side sessions, signed cookies
- **Role-Based Access**: Admin vs regular user permissions
- **API Protection**: Endpoint-level authentication checks

### **Network Security**
- **Reverse Proxy**: Caddy handles SSL termination and security headers
- **Admin Protection**: IP allowlist for administrative functions
- **CORS**: Controlled cross-origin requests
- **Input Validation**: SQL injection prevention, XSS protection

### **Data Protection**
- **Environment Variables**: Secrets never committed to code
- **Database Security**: Parameterized queries, connection pooling
- **Session Security**: Filesystem storage with signed tokens

---

## Development Workflow

### **Local Development (Replit)**
```bash
# Start development server
python main.py

# Install dependencies
pip install -r requirements.txt

# Database access via Replit's built-in PostgreSQL
```

### **Production Deployment**
```bash
# Deploy to lab environment
./lab-deploy.sh

# Manual deployment
docker-compose up -d --build

# View logs
docker-compose logs -f
```

### **Code Organization Standards**
- **Modular Design**: Each feature in separate blueprint
- **Service Layer**: Business logic separated from routes
- **Template Inheritance**: DRY principle for HTML templates
- **Error Handling**: Graceful degradation and user-friendly messages

---

## Key Business Logic

### **Options Sentiment Analysis**
The core business logic calculates "Bulls Want" and "Bears Want" prices:
- **Bulls Want**: Price level where call volume exceeds put volume
- **Bears Want**: Price level where put volume exceeds call volume
- **Market Bias**: Overall sentiment direction based on volume analysis

### **Watchlist Forecasting**
- **Multi-Symbol Analysis**: Analyze sentiment across entire watchlists
- **Expiration Cycles**: 4-cycle forward analysis
- **Risk Assessment**: Expected move calculations
- **Performance Tracking**: Historical accuracy metrics

---

## Integration Points

### **External Dependencies**
- **Polygon.io**: Primary data source requiring API key
- **PostgreSQL**: Database requiring connection parameters
- **Docker**: Container runtime for deployment
- **Caddy**: Reverse proxy for production traffic

### **Internal Modules Communication**
```
routes/api.py → services/polygon_service.py → Polygon.io API
routes/auth.py → services/database.py → PostgreSQL
templates/*.html → static/*.js → routes/api.py
```

---

## Monitoring & Maintenance

### **Health Checks**
- **Application**: `/api/health` endpoint
- **Database**: Connection verification in health check
- **External APIs**: Polygon.io connectivity validation

### **Logging**
- **Flask Logs**: Request/response logging with timestamps
- **Docker Logs**: `docker-compose logs -f` for debugging
- **Error Tracking**: Detailed exception handling and reporting

### **Performance Monitoring**
- **API Response Times**: Built-in timing for external calls
- **Database Performance**: Connection pooling and query optimization
- **Caching Strategy**: Market data caching with TTL

---

## Future Development Notes

### **Scalability Considerations**
- **Database**: Ready for connection pooling and read replicas
- **Caching**: Redis integration points identified
- **Load Balancing**: Caddy supports multiple backend instances

### **Feature Extensions**
- **Real-time Updates**: WebSocket integration points prepared
- **Mobile API**: RESTful design supports mobile app development
- **Analytics**: Event tracking infrastructure ready
- **Third-party Integrations**: Modular service layer supports additional APIs

---

## Handover Instructions

### **For Developers Taking Over**

1. **Environment Setup**:
   ```bash
   git clone [repository]
   cp .env.example .env  # Configure environment variables
   docker-compose up -d  # Start all services
   ```

2. **Key Files to Understand**:
   - `main.py` - Application entry point and configuration
   - `routes/` - All page logic and API endpoints
   - `services/polygon_service.py` - External API integration
   - `templates/base.html` - Site-wide navigation and layout

3. **Testing Changes**:
   ```bash
   # Development
   python main.py
   
   # Production testing
   ./lab-deploy.sh
   ```

4. **Common Tasks**:
   - **Add new page**: Create template, add route in appropriate blueprint
   - **Modify navigation**: Edit `templates/base.html`
   - **Add API endpoint**: Add to `routes/api.py`
   - **Database changes**: Modify `services/database.py`

### **For AI Assistants**
- **Architecture**: Modular Flask app with blueprints and service layer
- **Data Flow**: Routes → Services → External APIs → Database
- **Frontend**: Template inheritance with vanilla JavaScript
- **Deployment**: Docker Compose with Caddy reverse proxy
- **Authentication**: Session-based with role-based access control

---

**Last Updated**: September 8, 2025  
**Version**: 2.0 (Modular Architecture)  
**Maintainer**: Original Developer  
**Status**: Production Ready for Lab Environment