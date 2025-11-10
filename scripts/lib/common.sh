#!/bin/bash
# Shared helpers and environment for ECI scripts
set -e

# Resolve repo root (two levels up from lib)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
export ROOT_DIR

# Defaults (can be overridden by env)
PROJECT_NAME=${PROJECT_NAME:-"ECI E-Commerce Platform"}
SERVICES=${SERVICES:-"postgres redis customers products inventory orders payments shipments gateway dashboard"}
BASE_URL=${BASE_URL:-"http://localhost:8080"}
DASHBOARD_URL=${DASHBOARD_URL:-"http://localhost:8008"}
DEPENDENCY_CACHE_FILE=${DEPENDENCY_CACHE_FILE:-"$ROOT_DIR/.dependency_cache"}
DEBUG_MODE=${DEBUG:-0}

# Detect OS
OS_TYPE="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
  OS_TYPE="macos"
elif [[ "$OSTYPE" == "linux-gnu"* || "$OSTYPE" == "linux"* ]]; then
  if grep -qE "(Microsoft|WSL)" /proc/version 2>/dev/null; then
    OS_TYPE="wsl"
  else
    OS_TYPE="linux"
  fi
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
  OS_TYPE="git-bash"
fi
export OS_TYPE

# Compose detection (lazy)
DOCKER_COMPOSE_CMD=""
if command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE_CMD="docker-compose"
elif docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE_CMD="docker compose"
fi
export DOCKER_COMPOSE_CMD

# Debug logger
debug_log() {
  if [ "$DEBUG_MODE" = "1" ]; then
    echo "[DEBUG] $*" >&2
  fi
}

# Ensure compose variable is set
ensure_compose() {
  if [ -n "$DOCKER_COMPOSE_CMD" ]; then return 0; fi
  if command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker-compose"
  elif docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker compose"
  else
    return 1
  fi
export DOCKER_COMPOSE_CMD
}

# Build metadata for images used by docker compose
set_build_metadata() {
  # Idempotent: if already set, do nothing
  if [ -n "${RELEASE_ID:-}" ] && [ -n "${BUILD_TIME:-}" ]; then
    return 0
  fi
  local sha
  sha=$(git --no-pager rev-parse --short=12 HEAD 2>/dev/null || echo dev)
  export RELEASE_ID="$sha"
  export BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

# Configurable DB readiness timeout (seconds)
: "${DB_READY_TIMEOUT:=120}"
export DB_READY_TIMEOUT

# Wait for Postgres readiness with exponential backoff (1..5s)
wait_for_db() {
  ensure_compose || return 1
  local timeout="$DB_READY_TIMEOUT"
  local elapsed=0
  local delay=1
  echo "Waiting for database to be ready (timeout: ${timeout}s)..."
  while [ "$elapsed" -lt "$timeout" ]; do
    if $DOCKER_COMPOSE_CMD exec -T postgres pg_isready -U eci -d eci >/dev/null 2>&1; then
      debug_log "Database ready after ${elapsed}s"
      return 0
    fi
    sleep "$delay"
    elapsed=$((elapsed + delay))
    if [ "$delay" -lt 5 ]; then
      delay=$((delay * 2))
      [ "$delay" -gt 5 ] && delay=5
    fi
  done
  echo "Database readiness timed out after ${timeout}s" >&2
  return 1
}
