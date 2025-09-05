# Selling-Options.com Deployment Guide

## Overview
Professional options trading platform inspired by TipRanks, featuring live market data, options sentiment analysis, calculators, and administrative tools. Built with Flask (Python) backend and vanilla JavaScript frontend, designed for Docker deployment with PostgreSQL database.

## Application Features

### Core Features
- **Market Pulse Dashboard**: Live market data with real-time updates every 60 seconds
- **Options Calculator**: Interactive tool for calculating options premiums, Greeks, and profit/loss scenarios
- **Watchlist Forecast**: Analyze options sentiment across entire watchlists for next 4 expiration dates
- **Navigation Quote Search**: Real-time stock quote lookup from any page
- **User Authentication**: Secure registration, login/logout with session management
- **Admin System**: User management, watchlist administration, role-based access control

### Technical Features
- **Centralized Navigation**: Single source navigation system with automatic JavaScript inclusion
- **Responsive Design**: Mobile-first CSS Grid/Flexbox layout
- **Real-time Data**: Yahoo Finance API integration for live quotes and options chains
- **Session Management**: Flask-Session with filesystem storage
- **Security**: bcrypt password hashing, CSRF protection, role-based permissions
- **Error Handling**: Comprehensive error handling for financial data edge cases

## File Structure and Purpose

### Core Application Files
- **`app.py`** - Main Flask application with all routes, templates, and business logic
- **`requirements.txt`** - Python dependencies list
- **`nav.js`** - Centralized navigation JavaScript (quote search, event handlers)
- **`style.css`** - Complete CSS styling for entire application
- **`replit.md`** - Project documentation and architecture notes

### Frontend Files
- **`index.html`** - Homepage with market pulse dashboard
- **`calculator.html`** - Options calculator page
- **`calculator.js`** - Calculator-specific JavaScript functionality
- **`video-tutorials.html`** - Educational content page

### Configuration Files
- **`Dockerfile`** - Container build instructions for Flask app
- **`docker-compose.yml`** - Production deployment configuration
- **`docker-compose.lab.yml`** - Lab environment configuration
- **`Caddyfile`** - Reverse proxy configuration for production
- **`lab-deploy.sh`** - Automated deployment script for lab environment

### Assets
- **`attached_assets/generated_images/`** - Application logos and images
- **`favicon.ico`, `favicon-16x16.png`, `favicon-32x32.png`** - Browser icons
- **`flask_session/`** - Session storage directory (created at runtime)

## Dependencies

### Python Dependencies (requirements.txt)
```
Flask==2.3.3
Flask-Session==0.5.0
psycopg2-binary==2.9.7
bcrypt==4.0.1
yfinance==0.2.18
pandas==2.0.3
requests==2.31.0
```

### System Dependencies
- **Python 3.11+**
- **PostgreSQL 16** (containerized)
- **Docker & Docker Compose**
- **Caddy 2** (reverse proxy)

### JavaScript Dependencies
- **Vanilla JavaScript** (no external libraries)
- **Fetch API** for HTTP requests
- **DOM manipulation** for interactive features

## Database Schema

### Tables
1. **users** - User accounts (id, email, password_hash, created_at)
2. **admin_users** - Admin role assignments (id, user_id, granted_at)
3. **watchlist** - User watchlists (id, user_id, symbol, added_at)

### Database Features
- **PostgreSQL 16** with automatic table creation
- **bcrypt password hashing** for security
- **Session-based authentication**
- **Admin role system**

## Environment Variables

### Required for Production
```bash
DATABASE_URL=postgresql://user:password@host:port/database
FLASK_ENV=production
SECRET_KEY=your-secure-secret-key
```

### Optional
```bash
PGHOST=localhost
PGPORT=5432
PGUSER=postgres
PGPASSWORD=password
PGDATABASE=options_db
```

## Deployment Instructions

### Lab Environment (Automated)
```bash
chmod +x lab-deploy.sh
./lab-deploy.sh
```

### Manual Docker Deployment
```bash
# Build and start services
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Verify deployment
curl http://localhost/api/market-data
curl http://localhost/
```

### Production Considerations
1. **SSL/TLS**: Caddy handles automatic HTTPS certificates
2. **Database**: Use managed PostgreSQL service for production
3. **Secrets**: Use proper secret management (not environment files)
4. **Monitoring**: Add application monitoring and logging
5. **Backup**: Regular database backups required

## API Endpoints

### Public Endpoints
- `GET /` - Homepage
- `GET /login` - Login page
- `GET /signup` - Registration page
- `POST /login` - User authentication
- `POST /signup` - User registration

### Authenticated Endpoints
- `GET /calculator.html` - Options calculator
- `GET /forecast` - Watchlist forecast tool
- `GET /api/auth-status` - Authentication status
- `GET /api/quote?symbol=AAPL` - Stock quote lookup
- `GET /api/market-data` - Market dashboard data

### Admin Endpoints
- `GET /admin` - Admin dashboard
- `GET /admin/watchlists` - Watchlist management
- `POST /admin/watchlists` - Create watchlist
- `DELETE /admin/watchlists/delete/{id}` - Delete watchlist

## Security Features

### Authentication
- **Session-based authentication** with Flask-Session
- **bcrypt password hashing** (rounds=12)
- **CSRF protection** on forms
- **Role-based access control** (user/admin)

### Data Protection
- **SQL injection prevention** with parameterized queries
- **Input validation** and sanitization
- **Error message sanitization** (no sensitive data exposure)
- **Secure session configuration**

## Architecture Highlights

### Centralized Navigation System
- **Single source of truth** for navigation HTML (`generate_navigation()`)
- **Automatic JavaScript inclusion** via `nav.js`
- **Consistent styling** across all pages
- **Scalable design** - new pages automatically get navigation

### Responsive Design
- **Mobile-first approach** with CSS Grid/Flexbox
- **TipRanks-inspired styling** with modern financial platform aesthetics
- **Consistent color scheme** (blues, purples, professional grays)
- **Interactive elements** with hover effects and transitions

### Real-time Features
- **Live market data updates** every 60 seconds
- **Yahoo Finance API integration** for accurate quotes
- **Client-side data refresh** without page reloads
- **Error handling** for API failures

## Troubleshooting

### Common Issues
1. **Database connection failures**: Check DATABASE_URL and PostgreSQL status
2. **Static assets not loading**: Verify Docker volume mounts
3. **Session issues**: Ensure flask_session directory exists and is writable
4. **API errors**: Check Yahoo Finance API availability

### Health Checks
```bash
# Container status
docker-compose ps

# Application health
curl http://localhost/api/market-data

# Database connectivity
docker-compose exec db psql -U postgres -d options_db -c "SELECT 1;"
```

### Logs
```bash
# Application logs
docker-compose logs selling-options-app

# Database logs
docker-compose logs db

# Proxy logs
docker-compose logs caddy
```

## Development Notes

### Code Style
- **Python**: PEP 8 compliant, type hints where appropriate
- **JavaScript**: ES6+ features, async/await for API calls
- **HTML**: Semantic markup, accessibility considerations
- **CSS**: BEM-style naming, mobile-first responsive design

### Testing Considerations
- Test all authentication flows (login/logout/signup)
- Verify admin role restrictions work correctly
- Test market data API under various conditions
- Validate calculator accuracy with known option values
- Test navigation consistency across all pages

## Support Information

### Key Contacts
- Original development environment: Replit
- Database: PostgreSQL 16
- Reverse proxy: Caddy 2
- Container platform: Docker

### Documentation
- This deployment guide contains complete setup instructions
- `replit.md` contains additional architecture notes
- Inline code comments explain complex business logic
- API endpoints documented in Flask route decorators

---

## Quick Start Checklist for AI Assistant

1. **Verify system requirements**: Docker, Docker Compose, PostgreSQL access
2. **Review environment variables**: Set DATABASE_URL and SECRET_KEY
3. **Check file permissions**: Ensure lab-deploy.sh is executable
4. **Run deployment**: Execute `./lab-deploy.sh` for automated setup
5. **Test health checks**: Verify API endpoints respond correctly
6. **Create admin user**: Use Flask shell or direct database insert
7. **Test authentication**: Login/logout flows work correctly
8. **Verify features**: Market data, calculator, admin functions operational

The application is designed to be self-contained and should deploy successfully with minimal configuration once database connectivity is established.