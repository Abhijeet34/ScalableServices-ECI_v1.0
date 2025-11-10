#!/bin/bash
# ECI Platform - Universal Cross-Platform Launcher
# Orchestrates sub-commands split into dedicated scripts under scripts/

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
export DEBUG_MODE=${DEBUG:-0}

# Helper to run dependency install once for flows that require it
install_deps_once() {
  # First ensure dependencies (Docker CLI, docker-compose, etc.) are installed
  # This will also attempt to start Docker daemon if needed
  INSTALL_DEPS=1 bash "$ROOT_DIR/scripts/bin/install-deps.sh" check || {
    echo "" >&2
    echo "Dependency check failed. Please ensure:" >&2
    echo "  1. Docker Desktop is installed" >&2
    echo "  2. Docker Desktop is running" >&2
    echo "  3. Run: ./launcher.sh again" >&2
    exit 1
  }
  
  # Verify Docker daemon is actually running after dependency check
  if ! docker info >/dev/null 2>&1; then
    echo "" >&2
    echo "Docker daemon is not running!" >&2
    echo "" >&2
    echo "Please start Docker:" >&2
    case "${OSTYPE}" in
      darwin*)
        echo "  - If using Docker Desktop: Open Docker Desktop application" >&2
        echo "  - If using Colima: Run 'colima start'" >&2
        ;;
      msys|cygwin)
        echo "  - Open Docker Desktop application on Windows" >&2
        echo "  - Wait for Docker to fully start (whale icon in system tray)" >&2
        ;;
      linux*)
        echo "  - Run: sudo systemctl start docker" >&2
        echo "  - Or: sudo service docker start" >&2
        ;;
      *)
        echo "  - Start your Docker service/application" >&2
        ;;
    esac
    echo "" >&2
    echo "Then run ./launcher.sh again" >&2
    exit 1
  fi
  
  export LAUNCHER_BOOTSTRAPPED=1
}

show_menu() {
  echo ""
  echo "================================"
  echo "ECI E-Commerce Platform"
  echo "================================"
  echo "Docker Compose:"
  echo "  1) Start    2) Status   3) Logs"
  echo "  4) Restart  5) Stop     6) Tests"
  echo "  7) Validate 8) Reseed   9) Clean"
  echo ""
  echo "K) Kubernetes  D) Debug $([ \"$DEBUG_MODE\" = \"1\" ] && echo \"[ON]\" || echo \"[OFF]\")  0) Exit"
  echo "================================"
  echo -n "Select: "
}

k8s_menu() {
  while true; do
    echo ""
    echo "================================"
    echo "Kubernetes (k3d)"
    echo "================================"
    echo "  1) Deploy"
    echo "  2) Status"
    echo "  3) Delete Cluster"
    echo "  0) Back"
    echo "================================"
    echo -n "Select: "
    read -r kopt
    case $kopt in
      1)
        if [ -f "$ROOT_DIR/scripts/k8s/deploy-k8s.sh" ]; then
          bash "$ROOT_DIR/scripts/k8s/deploy-k8s.sh"
        else
          echo "K8s deployment script not found at scripts/k8s/deploy-k8s.sh"
        fi
        ;;
      2)
        if [ -f "$ROOT_DIR/scripts/k8s/deploy-k8s.sh" ]; then
          bash "$ROOT_DIR/scripts/k8s/deploy-k8s.sh" status
        else
          echo "K8s deployment script not found at scripts/k8s/deploy-k8s.sh"
        fi
        ;;
      3)
        if [ -f "$ROOT_DIR/scripts/k8s/deploy-k8s.sh" ]; then
          bash "$ROOT_DIR/scripts/k8s/deploy-k8s.sh" delete
        else
          echo "K8s deployment script not found at scripts/k8s/deploy-k8s.sh"
        fi
        ;;
      0)
        break
        ;;
      *)
        echo "Invalid option. Please try again."
        ;;
    esac
    echo ""
    read -p "Press Enter to continue..."
  done
}

show_help() {
  cat <<'EOF'
ECI Platform Launcher

Usage:
  launcher.sh [command]
  launcher.sh --help | -h | help
  launcher.sh --version
  launcher.sh                 # interactive menu

Commands:
  start       Start platform (runs dependency install once)
  stop        Stop platform
  restart     Stop then start
  status      Show service status
  logs        Tail service logs
  test        Run test suite (scripts/tests/test-suite.sh)
  validate    Validate and clean database
  reseed      Reseed database
  clean       Remove containers, networks, and volumes
  debug       Re-run with DEBUG=1 (toggles in interactive mode)
  help        Show this help
  version     Show launcher version

Env vars:
  DEBUG=1     Enable verbose output in scripts

Examples:
  ./launcher.sh start
  ./launcher.sh validate
  DEBUG=1 ./launcher.sh start
EOF
}

LAUNCHER_VERSION="1.0.0"

main() {
  # Only check dependencies once at startup for interactive mode
  install_deps_once

  while true; do
    show_menu
    read -r option
    case $option in
      1)
        bash "$ROOT_DIR/scripts/platform/manage.sh" start
        ;;
      2)
        bash "$ROOT_DIR/scripts/platform/manage.sh" status
        ;;
      3)
        bash "$ROOT_DIR/scripts/platform/manage.sh" logs
        ;;
      4)
        echo "Restarting platform (will drop tables and clean containers)..."
        bash "$ROOT_DIR/scripts/platform/manage.sh" restart
        ;;
      5)
        bash "$ROOT_DIR/scripts/platform/manage.sh" stop
        ;;
      6)
        if [ -f "$ROOT_DIR/scripts/tests/test-suite.sh" ]; then
          bash "$ROOT_DIR/scripts/tests/test-suite.sh"
        else
          echo "Test suite not found at scripts/tests/test-suite.sh"
        fi
        ;;
      7)
        bash "$ROOT_DIR/scripts/db/validate.sh"
        ;;
      8)
        bash "$ROOT_DIR/scripts/platform/manage.sh" reseed
        ;;
      9)
        bash "$ROOT_DIR/scripts/platform/manage.sh" clean
        ;;
      k|K)
        k8s_menu
        ;;
      d|D)
        if [ "$DEBUG_MODE" = "1" ]; then
          DEBUG_MODE=0
          export DEBUG=0
          echo "Debug mode disabled"
        else
          DEBUG_MODE=1
          export DEBUG=1
          echo "Debug mode enabled"
        fi
        sleep 1
        ;;
      0)
        echo "Exiting..."
        exit 0
        ;;
      *)
        echo "Invalid option. Please try again."
        ;;
    esac
  done
}

if [ "$#" -eq 0 ]; then
  main
else
  case "$1" in
    start)
      install_deps_once
      bash "$ROOT_DIR/scripts/platform/manage.sh" start
      ;;
    stop)
      # No dependency check needed for stop
      bash "$ROOT_DIR/scripts/platform/manage.sh" stop
      ;;
    restart)
      install_deps_once
      bash "$ROOT_DIR/scripts/platform/manage.sh" restart
      ;;
    status)
      # No dependency check needed for status
      bash "$ROOT_DIR/scripts/platform/manage.sh" status
      ;;
    logs)
      # No dependency check needed for logs
      bash "$ROOT_DIR/scripts/platform/manage.sh" logs
      ;;
    test)
      install_deps_once
      if [ -f "$ROOT_DIR/scripts/tests/test-suite.sh" ]; then
        bash "$ROOT_DIR/scripts/tests/test-suite.sh"
      else
        echo "Test suite not found at scripts/tests/test-suite.sh"
        exit 1
      fi
      ;;
    validate)
      # No dependency check needed for validate
      bash "$ROOT_DIR/scripts/db/validate.sh"
      ;;
    reseed)
      # No dependency check needed for reseed (assumes platform is running)
      bash "$ROOT_DIR/scripts/platform/manage.sh" reseed
      ;;
    clean)
      # No dependency check needed for clean
      bash "$ROOT_DIR/scripts/platform/manage.sh" clean
      ;;
    debug)
      export DEBUG=1
      DEBUG_MODE=1
      shift
      exec "$0" "$@"
      ;;
    -h|--help|help)
      show_help
      exit 0
      ;;
    --version)
      echo "launcher.sh ${LAUNCHER_VERSION}"
      exit 0
      ;;
    *)
      echo "Invalid command: $1" >&2
      echo ""
      show_help
      exit 1
      ;;
  esac
fi
