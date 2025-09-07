#!/bin/bash

# Selling-Options.com NAS Deployment Script
# This script sets up and deploys the container to your NAS

set -e

echo "🚀 Starting Selling-Options.com NAS Deployment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed and running
check_docker() {
    print_status "Checking Docker installation..."
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker is not running. Please start Docker service."
        exit 1
    fi
    
    print_success "Docker is installed and running"
}

# Check if docker-compose is available
check_compose() {
    print_status "Checking Docker Compose..."
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        print_error "Docker Compose is not available. Please install docker-compose."
        exit 1
    fi
    print_success "Docker Compose is available: $COMPOSE_CMD"
}

# Setup environment file
setup_env() {
    print_status "Setting up environment file..."
    
    if [ ! -f ".env" ]; then
        if [ -f ".env.nas" ]; then
            cp .env.nas .env
            print_success "Created .env from .env.nas template"
        else
            print_error ".env.nas template not found!"
            exit 1
        fi
    else
        print_warning ".env file already exists, skipping creation"
    fi
    
    # Check if POLYGON_API_KEY is set
    if grep -q "POLYGON_API_KEY=" .env && ! grep -q "POLYGON_API_KEY=your_key_here" .env; then
        print_success "Polygon API key found in .env file"
    else
        print_error "Please edit .env file and add your POLYGON_API_KEY"
        print_status "Opening .env file for editing..."
        exit 1
    fi
}

# Check port availability
check_ports() {
    print_status "Checking port availability..."
    
    PORTS=(80 443 5432)
    for port in "${PORTS[@]}"; do
        if netstat -tuln 2>/dev/null | grep -q ":$port "; then
            print_warning "Port $port is already in use"
            if [ "$port" = "80" ] || [ "$port" = "443" ]; then
                print_status "Will use alternative port 8080 for web access"
            fi
        else
            print_success "Port $port is available"
        fi
    done
}

# Stop existing containers
stop_existing() {
    print_status "Stopping any existing containers..."
    
    if [ -f "docker-compose.nas.yml" ]; then
        $COMPOSE_CMD -f docker-compose.nas.yml down 2>/dev/null || true
    fi
    
    # Remove any orphaned containers
    docker container prune -f 2>/dev/null || true
    
    print_success "Cleaned up existing containers"
}

# Build and start containers
deploy() {
    print_status "Building and starting containers..."
    
    # Use NAS-specific compose file
    if [ ! -f "docker-compose.nas.yml" ]; then
        print_error "docker-compose.nas.yml not found!"
        exit 1
    fi
    
    # Build the application
    print_status "Building application image..."
    $COMPOSE_CMD -f docker-compose.nas.yml build --no-cache
    
    # Start services
    print_status "Starting services..."
    $COMPOSE_CMD -f docker-compose.nas.yml up -d
    
    print_success "Containers started successfully!"
}

# Check deployment health
check_health() {
    print_status "Checking deployment health..."
    
    # Wait for services to start
    sleep 10
    
    # Check if containers are running
    if $COMPOSE_CMD -f docker-compose.nas.yml ps | grep -q "Up"; then
        print_success "Containers are running"
    else
        print_error "Some containers failed to start"
        print_status "Container logs:"
        $COMPOSE_CMD -f docker-compose.nas.yml logs
        exit 1
    fi
    
    # Test application endpoint
    sleep 5
    if curl -f http://localhost:8080 &> /dev/null || curl -f http://localhost:80 &> /dev/null; then
        print_success "Application is responding to HTTP requests"
    else
        print_warning "Application not responding yet (may need more startup time)"
    fi
}

# Show final status
show_status() {
    echo ""
    echo "🎉 Deployment Complete!"
    echo ""
    echo "Your Selling-Options.com platform is now running on your NAS:"
    echo ""
    echo "📊 Web Interface:"
    echo "   Primary:  http://your-nas-ip:80"
    echo "   Backup:   http://your-nas-ip:8080"
    echo ""
    echo "🗄️  Database:"
    echo "   Host: your-nas-ip:5432"
    echo "   Database: options_db"
    echo ""
    echo "📋 Management Commands:"
    echo "   View logs:    $COMPOSE_CMD -f docker-compose.nas.yml logs -f"
    echo "   Stop:         $COMPOSE_CMD -f docker-compose.nas.yml down"
    echo "   Restart:      $COMPOSE_CMD -f docker-compose.nas.yml restart"
    echo "   Update:       git pull && $COMPOSE_CMD -f docker-compose.nas.yml up -d --build"
    echo ""
}

# Main deployment flow
main() {
    echo "=================================="
    echo "🏗️  Selling-Options.com NAS Setup"
    echo "=================================="
    echo ""
    
    check_docker
    check_compose
    setup_env
    check_ports
    stop_existing
    deploy
    check_health
    show_status
}

# Run main function
main "$@"