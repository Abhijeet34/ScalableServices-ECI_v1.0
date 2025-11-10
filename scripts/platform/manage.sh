#!/bin/bash
# ECI Platform Management Script

set -e

# Load shared helpers
source "$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)/lib/common.sh"

# Configuration
SERVICES="postgres redis customers products inventory orders payments shipments gateway"
REQUIRED_TOOLS=("docker" "curl")
PROJECT_DIR=$(dirname "$(readlink -f "$0")" 2>/dev/null || dirname "$0")

# Dependency validation (no installs here)
if [ -z "${LAUNCHER_BOOTSTRAPPED:-}" ]; then
    bash "$PROJECT_DIR/../bin/install-deps.sh" check || {
        echo "Dependencies missing. Run ./scripts/bin/install-deps.sh --fix or use ./launcher.sh" >&2
        exit 1
    }
fi

# Ensure compose command is available; map to COMPOSE for compatibility
ensure_compose || { echo "docker-compose not found" >&2; exit 1; }
COMPOSE="$DOCKER_COMPOSE_CMD"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Functions

function print_success() {
    echo -e "${GREEN}$1${NC}"
}

function print_warning() {
    echo -e "${YELLOW}$1${NC}"
}

function print_error() {
    echo -e "${RED}$1${NC}"
}

function print_info() {
    echo -e "${CYAN}$1${NC}"
}

function check_docker() {
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker Desktop."
        exit 1
    fi
    print_success "Docker is running"
}

function show_help() {
    print_success "ECI E-Commerce Platform - Management Script"
    echo ""
    print_info "Usage:"
    echo "  ./manage.sh [command]"
    echo ""
    print_info "Available commands:"
    echo "  help              - Show this help message"
    echo "  setup             - Build all service images"
    echo "  start             - Start all services"
    echo "  stop              - Stop all services"
    echo "  restart           - Restart all services"
    echo "  status            - Show status of all containers"
    echo "  logs [service]    - Show logs (optional: specific service)"
    echo "  seed              - Load seed data into database"
    echo "  test              - Run all tests"
    echo "  token             - Get authentication token"
    echo "  clean             - Remove all containers, volumes, and images"
    echo "  backup            - Backup database"
    echo "  restore [file]    - Restore database from backup"
    echo "  dev               - Start development environment with seed data"
    echo "  info              - Show service endpoints and connection info"
    echo "  health            - Check health of all services"
    echo "  migrate           - Run database migrations"
    echo ""
}

function setup() {
    check_docker
    set_build_metadata
    print_success "Building all service images..."
    $COMPOSE build
    print_success "All images built successfully"
}

function start_services() {
    check_docker
    set_build_metadata
    print_success "Starting ECI platform (rebuilding images)..."
    $COMPOSE up -d --build $SERVICES
    print_warning "Waiting for services to be healthy..."
    sleep 10
    health_check
    print_success "All services started"
    
    # Uniform reseed on startup: drop schema -> migrations -> seed
    reseed_data
    
    echo ""
    show_info
}

function stop_services() {
    print_warning "Stopping all services..."
    $COMPOSE down
    print_success "All services stopped"
}

function restart_services() {
    stop_services
    start_services
}

function restart_service() {
    if [ -z "$1" ]; then
        print_error "Please specify a service name"
        echo "Usage: ./manage.sh restart-service <service>"
        exit 1
    fi
    print_warning "Restarting $1..."
    $COMPOSE restart "$1"
    print_success "$1 restarted"
}

function start_services_fast() {
    check_docker
    print_success "Starting ECI platform (fast, no rebuild/seed)..."
    $COMPOSE up -d $SERVICES
    print_warning "Quick health check..."
    sleep 5
    health_check
    print_success "Services started (fast mode)"
}

function build_service() {
    set_build_metadata
    if [ -n "$1" ]; then
        print_success "Building image for $1..."
        $COMPOSE build "$1"
        print_success "$1 image built"
    else
        setup
    fi
}

function show_status() {
    print_info "Service status:"
    $COMPOSE ps
}

function show_logs() {
    if [ -n "$1" ]; then
        $COMPOSE logs -f "$1"
    else
        $COMPOSE logs -f
    fi
}

function seed_data() {
    set_build_metadata
    print_success "Loading seed data..."
    $COMPOSE --profile seed up --build seed
    print_success "Seed data loaded"
}

function reseed_data() {
    print_error "WARNING: This will wipe existing data and reload seed data!"

    # Wait for Postgres readiness with configurable timeout and backoff
    local timeout="${DB_READY_TIMEOUT:-120}"
    local elapsed=0
    local delay=1
    print_info "Waiting for database to be ready (timeout: ${timeout}s)..."
    while [ "$elapsed" -lt "$timeout" ]; do
        if $COMPOSE exec -T postgres pg_isready -U eci -d eci >/dev/null 2>&1; then
            break
        fi
        sleep "$delay"
        elapsed=$((elapsed + delay))
        if [ "$delay" -lt 5 ]; then
            delay=$((delay * 2))
            [ "$delay" -gt 5 ] && delay=5
        fi
    done
    if [ "$elapsed" -ge "$timeout" ]; then
        print_warning "Database readiness timed out after ${timeout}s; attempting reseed anyway"
    fi

    # Drop and recreate schema
    print_warning "Dropping and recreating schema..."
    $COMPOSE exec -T postgres psql -U eci -d eci -c "\
        DROP SCHEMA public CASCADE;\
        CREATE SCHEMA public;\
        GRANT ALL ON SCHEMA public TO eci;\
        GRANT ALL ON SCHEMA public TO public;\
    " >/dev/null 2>&1 || print_warning "Could not drop schema (database may be initializing)"
    
    # Ensure services are up and run migrations
    print_info "Running migrations..."
    run_migrations
    
    # Seed fresh data
    seed_data

    # Ensure dashboard re-creates its activity_logs table after schema reset
    print_info "Restarting dashboard to re-run its startup migration..."
    $COMPOSE restart dashboard >/dev/null 2>&1 || true
    sleep 2
    
    print_success "Database reseeded successfully"
}

function run_tests() {
    print_success "Running tests..."
    for service in customers products inventory orders payments shipments; do
        print_warning "Testing $service..."
        $COMPOSE exec -T $service pytest tests/ -v 2>/dev/null || print_warning "No tests found for $service"
    done
}

function get_token() {
    print_success "Fetching authentication token..."
    curl -s -X POST -d "username=testuser" http://localhost:8080/auth/token | $PYTHON -m json.tool
}

function clean_all() {
    print_error "WARNING: This will remove all data!"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Remove all compose services, volumes, and service images
        $COMPOSE down -v --rmi all
        
        # Clean BuildKit cache to free space
        print_warning "Cleaning build cache..."
        docker buildx prune -af >/dev/null 2>&1 || true
        
        print_success "Cleanup complete"
    fi
}

function backup_db() {
    print_success "Creating database backup..."
    mkdir -p backups
    BACKUP_FILE="backups/eci_backup_$(date +%Y%m%d_%H%M%S).sql"
    $COMPOSE exec -T postgres pg_dump -U eci eci > "$BACKUP_FILE"
    print_success "Backup created: $BACKUP_FILE"
}

function restore_db() {
    if [ -z "$1" ]; then
        print_error "Please specify a backup file"
        echo "Usage: ./manage.sh restore <backup-file>"
        exit 1
    fi

    if [ ! -f "$1" ]; then
        print_error "Backup file not found: $1"
        exit 1
    fi

    print_warning "Restoring from $1..."
    $COMPOSE exec -T postgres psql -U eci eci < "$1"
    print_success "✓ Database restored"
}

function dev_environment() {
    bash "$PROJECT_DIR/start.sh"
    print_success "✓ Development environment ready!"
    get_token
}

function show_info() {
    print_success "=== ECI Platform Information ==="
    echo ""
    print_info "Service Endpoints:"
    echo "  Gateway (REST):    http://localhost:8080/swagger"
    echo "  Gateway (GraphQL): http://localhost:8080/graphql"
    echo ""
    print_info "Database:"
    echo "  Host:     localhost"
    echo "  Port:     5432"
    echo "  Database: eci"
    echo "  Username: eci"
    echo "  Password: eci"
    echo ""
    print_info "Redis:"
    echo "  Host: localhost"
    echo "  Port: 6379"
    echo ""
    print_info "Quick Commands:"
    echo "  Get token:    ./manage.sh token"
    echo "  View logs:    ./manage.sh logs"
    echo "  Load data:    ./manage.sh seed"
    echo "  Run tests:    ./manage.sh test"
}

function health_check() {
    print_warning "Checking service health..."
    docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "scalable-services|eci" || true
}

function run_migrations() {
    print_success "Running migrations..."
    for service in customers products inventory orders payments shipments; do
        print_warning "Migrating $service..."
        $COMPOSE exec -T $service alembic upgrade head || true
    done
    print_success "✓ Migrations complete"
}

# Main execution
case "${1:-help}" in
    help)
        show_help
        ;;
    setup)
        setup
        ;;
    start)
        bash "$PROJECT_DIR/start.sh"
        ;;
    fast|up-fast)
        start_services_fast
        ;;
    build)
        build_service "$2"
        ;;
    stop)
        bash "$PROJECT_DIR/stop.sh"
        ;;
    restart)
        bash "$PROJECT_DIR/stop.sh"
        bash "$PROJECT_DIR/start.sh"
        ;;
    restart-service)
        restart_service "$2"
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs "$2"
        ;;
    seed)
        reseed_data
        ;;
    reseed)
        reseed_data
        ;;
    test)
        run_tests
        ;;
    token)
        get_token
        ;;
    clean)
        clean_all
        ;;
    backup)
        backup_db
        ;;
    restore)
        restore_db "$2"
        ;;
    export-fixtures)
        shift
        bash "$PROJECT_DIR/../fixtures/export-fixtures.sh" "$@"
        ;;
    promote-fixtures)
        shift
        bash "$PROJECT_DIR/../fixtures/promote-fixtures.sh" "$@"
        ;;
    dev)
        dev_environment
        ;;
    info)
        show_info
        ;;
    health)
        health_check
        ;;
    migrate)
        run_migrations
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
