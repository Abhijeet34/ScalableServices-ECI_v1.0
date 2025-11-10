#!/bin/bash
set -e
source "$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)/lib/common.sh"

echo "Checking for port conflicts..."
PORTS=("5432" "6379" "8080" "8008")
PORT_SERVICES=("postgres" "redis" "gateway" "dashboard")
CONFLICTS_FOUND=0

for i in "${!PORTS[@]}"; do
  PORT="${PORTS[$i]}"; SERVICE="${PORT_SERVICES[$i]}"
  CONTAINER_ID=""
  case "$OS_TYPE" in
    macos|linux|wsl|git-bash)
      CONTAINER_ID=$(docker ps -q --filter "publish=$PORT" 2>/dev/null || true)
      ;;
  esac
  if [ -n "$CONTAINER_ID" ]; then
    CONTAINER_NAME=$(docker inspect --format='{{.Name}}' "$CONTAINER_ID" 2>/dev/null | sed 's/^\///' || echo "unknown")
    if ! echo "$CONTAINER_NAME" | grep -q "scalableservices\|eci"; then
      echo "  Port $PORT in use by container: $CONTAINER_NAME"
      CONFLICTS_FOUND=1
      read -r -p "  Stop conflicting container? (y/n): " RESPONSE
      if [[ "$RESPONSE" =~ ^[Yy]$ ]]; then
        docker stop "$CONTAINER_ID" >/dev/null 2>&1 || true
        echo "  Stopped."
      fi
    fi
  else
    PID=""
    case "$OS_TYPE" in
      macos) PID=$(lsof -ti:"$PORT" 2>/dev/null || true) ;;
      linux|wsl)
        PID=$(ss -lptn "sport = :$PORT" 2>/dev/null | grep -v "^State" | awk '{print $6}' | grep -o 'pid=[0-9]*' | cut -d= -f2 | head -1 || true)
        [ -z "$PID" ] && PID=$(lsof -ti:"$PORT" 2>/dev/null || true)
        ;;
      git-bash) PID=$(netstat -ano | grep ":$PORT " | grep "LISTENING" | awk '{print $5}' | head -1 || true) ;;
    esac
    if [ -n "$PID" ]; then
      echo "  Port $PORT in use by PID: $PID"
      CONFLICTS_FOUND=1
      read -r -p "  Kill this process? (y/n): " RESPONSE
      if [[ "$RESPONSE" =~ ^[Yy]$ ]]; then
        case "$OS_TYPE" in
          macos|linux|wsl)
            kill "$PID" 2>/dev/null || sudo kill "$PID" 2>/dev/null || true
            sleep 1
            ps -p "$PID" >/dev/null 2>&1 && (kill -9 "$PID" 2>/dev/null || sudo kill -9 "$PID" 2>/dev/null || true)
            ;;
          git-bash)
            cmd.exe /c "taskkill /PID $PID /F" 2>/dev/null || true
            ;;
        esac
      fi
    fi
  fi
done

[ "$CONFLICTS_FOUND" -eq 0 ] && echo "  No port conflicts detected." || echo "  Port conflict check complete."
