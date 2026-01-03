# Environment variables for NAS deployment
# Copy this to .env on your NAS before running docker-compose

# Polygon.io API Key (REQUIRED - without this, container will restart continuously)
POLYGON_API_KEY=SgahyvybcxIY8IG9vPM9QKYkF9mnbJGi

# Database Configuration
DATABASE_URL=postgresql://postgres:SecurePassword123@db:5432/options_db
POSTGRES_DB=options_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=SecurePassword123
PGHOST=db
PGDATABASE=options_db
PGUSER=postgres
PGPASSWORD=SecurePassword123
PGPORT=5432

# Flask Configuration
FLASK_ENV=production
FLASK_APP=main.py
SECRET_KEY=your-super-secret-key-change-this-in-production

# Application Settings
APP_HOST=0.0.0.0
APP_PORT=5000
APP_DEBUG=false

# Optional: Custom domain for your NAS
# DOMAIN=selling-options.your-nas-domain.com