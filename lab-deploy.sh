#!/bin/bash
# Lab deployment script for Market Pulse / Selling Options
# Designed to work with your NAS Caddy setup

set -e

echo "🚀 Deploying Market Pulse to Lab Environment..."

# Build and deploy
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10

# Health checks
echo "🔍 Running health checks..."

# Check if containers are running
if docker-compose ps | grep -q "Up"; then
    echo "✅ Containers are running"
else
    echo "❌ Some containers failed to start"
    docker-compose logs
    exit 1
fi

# Check app health
if curl -f http://localhost/api/market-data > /dev/null 2>&1; then
    echo "✅ API is responding"
else
    echo "⚠️  API health check failed (may need a moment to initialize)"
fi

# Check web interface
if curl -f http://localhost/ > /dev/null 2>&1; then
    echo "✅ Web interface is accessible"
else
    echo "⚠️  Web interface check failed"
fi

echo ""
echo "🎯 Deployment Summary:"
echo "   Web Interface: http://localhost/"
echo "   API Endpoint:  http://localhost/api/"
echo "   Database:      PostgreSQL (internal)"
echo ""
echo "🔧 Management commands:"
echo "   View logs:     docker-compose logs -f"
echo "   Stop:          docker-compose down"
echo "   Restart:       docker-compose restart"
echo ""
echo "✨ Market Pulse is ready in your lab environment!"