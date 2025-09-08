#!/usr/bin/env bash
set -euo pipefail
ENV_DIR="/volume1/docker/selling-options-lab"
cd "$ENV_DIR"

# sanity: required files
test -f docker-compose.yml && test -f .env

# pull latest image from GHCR and restart only the app
docker-compose pull selling-options-lab-app
docker-compose up -d selling-options-lab-app

# show status
docker-compose ps

echo "✅ Deploy complete! App restarted with latest image."