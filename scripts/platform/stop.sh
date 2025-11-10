#!/bin/bash
set -e
source "$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)/lib/common.sh"

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not running. Services are already stopped."
  if [ "$OS_TYPE" = "macos" ] && command -v colima >/dev/null 2>&1; then
    if ! colima status >/dev/null 2>&1; then echo "Colima is already stopped."; fi
  fi
  echo "Nothing to stop."
  exit 0
fi

ensure_compose || { echo "docker-compose not found"; exit 0; }

if docker ps --format '{{.Names}}' | grep -q 'postgres'; then
  $DOCKER_COMPOSE_CMD exec -T postgres psql -U eci -d eci -c "\
    DROP SCHEMA public CASCADE;\
    CREATE SCHEMA public;\
    GRANT ALL ON SCHEMA public TO eci;\
    GRANT ALL ON SCHEMA public TO public;\
  " >/dev/null 2>&1 || true
fi

$DOCKER_COMPOSE_CMD down

echo "Removing all containers..."
docker ps -a --filter "name=scalableservices" --format '{{.ID}}' | xargs -r docker rm -f 2>/dev/null || true
docker ps -a --filter "name=eci" --format '{{.ID}}' | xargs -r docker rm -f 2>/dev/null || true

if [ "$OS_TYPE" = "macos" ] && command -v colima >/dev/null 2>&1; then
  echo "Stopping Docker service (Colima)..."
  colima stop 2>/dev/null || echo "Colima already stopped or not running."
fi

echo "All services stopped and cleaned."
