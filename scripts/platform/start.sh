#!/bin/bash
set -e
source "$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)/lib/common.sh"

# Check if Docker CLI exists before attempting any Docker commands
if ! command -v docker >/dev/null 2>&1; then
  echo "Error: Docker is not installed!" >&2
  echo "" >&2
  echo "Please install Docker and run the launcher:" >&2
  echo "  ./launcher.sh start" >&2
  echo "" >&2
  echo "The launcher will guide you through dependency setup." >&2
  exit 1
fi

# Ensure Docker daemon (in case user calls directly)
if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not running. Starting..."
  case "$OS_TYPE" in
    macos)
      if command -v colima >/dev/null 2>&1; then
        echo "Starting Colima (Docker runtime)..."
        colima start 2>/dev/null || colima start
        echo "Waiting for Docker to be ready..."; sleep 5
      fi
      ;;
    linux|wsl)
      sudo systemctl start docker 2>/dev/null || sudo service docker start 2>/dev/null || true
      ;;
  esac
  for i in {1..30}; do docker info >/dev/null 2>&1 && break; sleep 1; done
fi

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

bash "$ROOT_DIR/scripts/bin/check-port-conflicts.sh"
bash "$ROOT_DIR/scripts/seed/validate.sh"

ensure_compose || { echo "docker-compose not found"; exit 1; }

# Export build metadata for compose builds
set_build_metadata

echo "Starting $PROJECT_NAME..."
$DOCKER_COMPOSE_CMD up -d $SERVICES

echo "Waiting for services to be healthy..."; sleep 10
for service in $SERVICES; do
  if $DOCKER_COMPOSE_CMD ps | grep -q "$service.*Up"; then
    echo "  $service: Running"
  else
    echo "  $service: Failed to start"
  fi
done

# Ensure Postgres is ready before dropping schema
wait_for_db || echo "Database readiness timed out; proceeding cautiously"

echo "Preparing database (drop & recreate schema)..."
$DOCKER_COMPOSE_CMD exec -T postgres psql -U eci -d eci -c "\
  DROP SCHEMA public CASCADE;\
  CREATE SCHEMA public;\
  GRANT ALL ON SCHEMA public TO eci;\
  GRANT ALL ON SCHEMA public TO public;\
" >/dev/null 2>&1 || echo "Note: Database might not be ready yet."

# Run database migrations to recreate schema/indexes uniformly
echo "Running migrations..."
for svc in customers products inventory orders payments shipments; do
  $DOCKER_COMPOSE_CMD exec -T "$svc" alembic upgrade head >/dev/null 2>&1 || true
  echo "  - $svc: migrations attempted"
done

echo "Loading seed data..."
$DOCKER_COMPOSE_CMD run --rm seed

echo "Seed data loaded successfully!"

# IMPORTANT: restarting dashboard so it reruns its startup migration after schema reset
# Without this, the activity_logs table may be missing until a manual restart
echo "Restarting dashboard to re-run migrations..."
$DOCKER_COMPOSE_CMD restart dashboard >/dev/null 2>&1 || true
sleep 2

echo ""; echo "Getting authentication token..."
TOKEN=$(curl -s -X POST "$BASE_URL/auth/token" -d "username=testuser" | grep -o '"access_token":"[^"]*' | sed 's/"access_token":"//')
if [ -n "$TOKEN" ]; then
  echo "Platform is ready!"
  echo "================================"
  echo "Service URLs:"
  echo "  Dashboard: $DASHBOARD_URL"
  echo "  REST API:  $BASE_URL/swagger"
  echo "  GraphQL:   $BASE_URL/graphql"
  echo "  Database:  localhost:5432 (user: eci, pass: eci)"
  echo ""
  echo "Authentication Token:"
  echo "  $TOKEN"
  echo ""
  echo "Quick Test:"
  echo "  curl -H \"Authorization: Bearer $TOKEN\" $BASE_URL/customers/"
  echo "================================"
else
  echo "Warning: Could not get authentication token. Services may still be starting."
fi
