# Replace selling-options-lab.com Environment

## Step-by-Step Instructions

### Step 1: Backup Current Lab (Optional Safety)
```bash
# SSH into your Synology NAS
ssh admin@192.168.217.150

# Backup current lab directory
sudo cp -r /volume1/docker/selling-options-lab /volume1/docker/selling-options-lab.backup.$(date +%Y%m%d)
```

### Step 2: Stop Current Lab Environment
```bash
cd /volume1/docker/selling-options-lab
sudo docker compose down
sudo docker system prune -f  # Clean up unused containers/images
```

### Step 3: Replace Lab Files
```bash
# Remove old files (keep directory structure)
sudo rm -rf /volume1/docker/selling-options-lab/*

# Copy new Market Pulse files to lab directory
# (You'll upload the new files via DSM File Station or SCP)
```

### Step 4: Upload New Files to /volume1/docker/selling-options-lab/
Upload these files from your Replit project:
- `Dockerfile`
- `docker-compose.lab.yml` (rename to `compose.yaml`)
- `requirements.txt`
- `app.py`
- `index.html`
- `calculator.html`
- `calculator.js`
- `video-tutorials.html`
- `style.css`
- `favicon.ico`
- `favicon-32x32.png`
- `favicon-16x16.png`
- `attached_assets/` folder (entire folder)

### Step 5: Set Up Lab Environment
```bash
cd /volume1/docker/selling-options-lab

# Rename the compose file
sudo mv docker-compose.lab.yml compose.yaml

# Create flask session directory
sudo mkdir -p flask_session
sudo chown 1000:1000 flask_session

# Build and start the new environment
sudo docker compose up -d --build
```

### Step 6: Initialize Database
```bash
# Wait for containers to start
sleep 30

# Initialize the database with admin user
sudo docker exec -it selling-options-lab-app python3 -c "
from app import create_tables
create_tables()
print('✅ Database initialized')
"

# Create admin user
sudo docker exec -it selling-options-lab-app python3 -c "
from app import create_admin_user
create_admin_user('admin@lab.com', 'admin123')
print('✅ Admin user created: admin@lab.com / admin123')
"
```

### Step 7: Verify Deployment
```bash
# Check container status
sudo docker compose ps

# Check logs
sudo docker compose logs -f selling-options-lab-app

# Test local access (should show JSON response)
curl -i http://localhost:5082/api/market-data

# Test web interface
curl -i http://localhost:5082/
```

### Step 8: Test via DSM Reverse Proxy
1. Open browser
2. Navigate to `https://selling-options-lab.com`
3. Should see your Market Pulse dashboard
4. Test login with: `admin@lab.com` / `admin123`
5. Test Options Calculator and Watchlist Forecast

## Expected Result
- ✅ `selling-options-lab.com` now shows Market Pulse interface
- ✅ All features working: Calculator, Watchlist, Admin, Video Tutorials
- ✅ PostgreSQL database with admin functionality
- ✅ Same DSM reverse proxy configuration (no changes needed)
- ✅ Using existing port 5082 as configured

## Troubleshooting
- **502 Bad Gateway**: Check if containers are running with `docker compose ps`
- **Database connection errors**: Check database logs with `docker compose logs lab-db`
- **Port conflicts**: Ensure no other service is using port 5082
- **Permission errors**: Check flask_session directory ownership