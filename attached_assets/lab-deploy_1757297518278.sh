#!/usr/bin/env bash
set -euo pipefail
ENV_DIR="/volume1/docker/selling-options-lab"
cd "$ENV_DIR"

# sanity: required files
test -f compose.ghcr.yml && test -f compose.run.yml && test -f .env

# pull latest image from GHCR and restart only the app
docker compose -f compose.ghcr.yml -f compose.run.yml pull selling-options-lab-app
docker compose -f compose.ghcr.yml -f compose.run.yml up -d selling-options-lab-app

# show status
docker compose -f compose.ghcr.yml -f compose.run.yml ps
