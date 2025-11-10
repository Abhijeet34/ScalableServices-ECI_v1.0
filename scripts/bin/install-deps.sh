#!/bin/bash
# Install and validate core dependencies (Docker, docker-compose/buildx, Colima)
# Also manages dependency cache
set -e
source "$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)/lib/common.sh"

# Handle command-line arguments
COMMAND="${1:-check}"
INSTALL_MODE=0 # 1 = allow installs (same as --fix or INSTALL_DEPS=1)
if [ "$COMMAND" = "fix" ] || [ "$COMMAND" = "--fix" ]; then
  INSTALL_MODE=1
  COMMAND="check"
fi
if [ "${INSTALL_DEPS:-0}" = "1" ]; then
  INSTALL_MODE=1
fi

show_help() {
  cat <<'EOF'
Dependency Manager - Install dependencies and manage cache

Usage:
  install-deps.sh [command]
  INSTALL_DEPS=1 install-deps.sh check   # enable install/repair mode

Commands:
  check       Check and install dependencies (default)
  fix|--fix   Run checks and actively install missing tools
  status      Show dependency and cache status
  clear       Clear dependency cache
  refresh     Force refresh (clear cache and check)
  help        Show this help

Cache:
  Dependencies are cached for 4 hours to speed up subsequent runs.
  Cache is automatically ignored if Docker daemon is not running.

EOF
}

show_status() {
  echo "Dependency Status:"
  echo "=================="
  
  # Check Docker
  if command -v docker >/dev/null 2>&1; then
    echo "  Docker CLI: ✓ Installed"
    if docker info >/dev/null 2>&1; then
      echo "  Docker Daemon: ✓ Running"
    else
      echo "  Docker Daemon: ✗ Not running"
    fi
  else
    echo "  Docker: ✗ Not installed"
  fi
  
  # Check docker-compose
  if command -v docker-compose >/dev/null 2>&1; then
    echo "  docker-compose: ✓ Installed (standalone)"
  elif docker compose version >/dev/null 2>&1; then
    echo "  docker-compose: ✓ Installed (plugin)"
  else
    echo "  docker-compose: ✗ Not installed"
  fi
  
  # Cache status
  echo ""
  echo "Cache Status:"
  echo "============="
  if [ -f "$DEPENDENCY_CACHE_FILE" ]; then
    local cache_time=$(stat -f %m "$DEPENDENCY_CACHE_FILE" 2>/dev/null || stat -c %Y "$DEPENDENCY_CACHE_FILE" 2>/dev/null || echo 0)
    local current_time=$(date +%s)
    local age=$((current_time - cache_time))
    local age_hours=$((age / 3600))
    local age_mins=$(((age % 3600) / 60))
    
    echo "  File: $DEPENDENCY_CACHE_FILE"
    echo "  Age: ${age_hours}h ${age_mins}m"
    
    if [ "$age" -lt 14400 ]; then
      local remaining=$((14400 - age))
      echo "  Status: VALID (${remaining}s remaining)"
    else
      echo "  Status: EXPIRED"
    fi
  else
    echo "  Status: No cache file"
  fi
}

clear_cache() {
  if [ -f "$DEPENDENCY_CACHE_FILE" ]; then
    rm "$DEPENDENCY_CACHE_FILE"
    echo "Dependency cache cleared"
  else
    echo "No cache to clear"
  fi
}

# Handle commands
case "$COMMAND" in
  status)
    show_status
    exit 0
    ;;
  clear)
    clear_cache
    exit 0
    ;;
  refresh)
    clear_cache
    echo "Running fresh dependency check..."
    # Continue to main check
    ;;
  help|-h|--help)
    show_help
    exit 0
    ;;
  check)
    # Continue to main check
    ;;
  *)
    echo "Unknown command: $COMMAND"
    show_help
    exit 1
    ;;
  esac

check_dependencies_cached() {
  # Skip cache check if Docker CLI is not installed
  if ! command -v docker >/dev/null 2>&1; then
    debug_log "Docker CLI not found, skipping cache"
    return 1
  fi
  
  # Skip cache check entirely if Docker daemon is not running
  if ! docker info >/dev/null 2>&1; then
    debug_log "Docker daemon not running, skipping cache"
    return 1
  fi
  
  if [ -f "$DEPENDENCY_CACHE_FILE" ]; then
    CACHE_TIME=$(stat -f %m "$DEPENDENCY_CACHE_FILE" 2>/dev/null || stat -c %Y "$DEPENDENCY_CACHE_FILE" 2>/dev/null || echo 0)
    CURRENT_TIME=$(date +%s)
    AGE=$((CURRENT_TIME - CACHE_TIME))
    # Reduced cache time to 4 hours (14400 seconds) for better reliability
    if [ "$AGE" -lt 14400 ]; then
      debug_log "Using cached dependency check (age: ${AGE}s)"
      return 0
    else
      debug_log "Cache expired (age: ${AGE}s)"
    fi
  fi
  return 1
}

mark_dependencies_checked() {
  touch "$DEPENDENCY_CACHE_FILE"
  debug_log "Dependencies cached"
}

# Networking helpers (prefer curl; fallback to wget)
set_fetch() {
  if command -v curl >/dev/null 2>&1; then
    FETCH="curl -fsSL"
    DOWNLOAD_WITH="curl"
    return 0
  fi
  if command -v wget >/dev/null 2>&1; then
    FETCH="wget -qO-"
    DOWNLOAD_WITH="wget"
    return 0
  fi
  return 1
}

install_curl_if_needed() {
  set_fetch && return 0
  if [ "$INSTALL_MODE" != "1" ]; then
    echo "curl/wget not found. Re-run with --fix or INSTALL_DEPS=1, or install curl manually."
    exit 1
  fi
  echo "Installing curl..."
  case "$OS_TYPE" in
    macos)
      if command -v brew >/dev/null 2>&1; then
        brew install curl
      else
        echo "Installing Homebrew first..."
        /bin/bash -c "$($(command -v /usr/bin/curl >/dev/null 2>&1 && echo "/usr/bin/curl -fsSL" || echo "$(command -v curl >/dev/null 2>&1 && echo "curl -fsSL" || echo "")") https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || {
          echo "Failed to bootstrap Homebrew automatically. Install curl manually."; exit 1; }
        brew install curl
      fi
      ;;
    linux|wsl)
      if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update -y && sudo apt-get install -y curl
      elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y curl
      elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm curl
      else
        echo "Please install curl using your distro's package manager."; exit 1
      fi
      ;;
    git-bash)
      echo "Please install curl via Chocolatey: choco install curl, then re-run."; exit 1
      ;;
  esac
  set_fetch || { echo "curl installation failed or not on PATH"; exit 1; }
}

# Download URL to file path (uses curl or wget)
download_to() {
  local path="$1" url="$2"
  
  # Ensure DOWNLOAD_WITH is set before attempting download
  if [ -z "$DOWNLOAD_WITH" ]; then
    set_fetch || install_curl_if_needed
  fi
  
  case "$DOWNLOAD_WITH" in
    curl)
      curl -fsSL "$url" -o "$path"
      ;;
    wget)
      wget -q "$url" -O "$path"
      ;;
    *)
      echo "ERROR: No download utility available (curl/wget). Cannot download."
      exit 1
      ;;
  esac
}

# ============================================================================
# PHASE 1: Package Manager Installation
# ============================================================================

# Install Chocolatey on Windows/Git Bash if not present
install_chocolatey_if_needed() {
  if command -v choco >/dev/null 2>&1; then
    return 0
  fi
  
  if [ "$OS_TYPE" != "git-bash" ]; then
    return 0
  fi
  
  if [ "$INSTALL_MODE" != "1" ]; then
    echo "Chocolatey not found. Re-run with --fix or INSTALL_DEPS=1 to install automatically."
    exit 1
  fi
  
  echo "Installing Chocolatey (Windows package manager)..."
  echo "This requires administrator privileges."
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))" || {
    echo "Chocolatey installation failed. Please install manually from https://chocolatey.org/install"
    exit 1
  }
  
  # Add Chocolatey to PATH for current session
  export PATH="$PATH:/c/ProgramData/chocolatey/bin"
  
  if ! command -v choco >/dev/null 2>&1; then
    echo "Chocolatey installation failed or not on PATH"
    echo "You may need to restart your terminal."
    exit 1
  fi
  
  echo "Chocolatey installed successfully"
}

# Install Homebrew on macOS if not present
install_homebrew_if_needed() {
  if command -v brew >/dev/null 2>&1; then
    return 0
  fi
  
  if [ "$OS_TYPE" != "macos" ]; then
    return 0
  fi
  
  if [ "$INSTALL_MODE" != "1" ]; then
    echo "Homebrew not found. Re-run with --fix or INSTALL_DEPS=1 to install automatically."
    exit 1
  fi
  
  echo "Installing Homebrew (macOS package manager)..."
  # Use system curl which is always available on macOS
  if command -v /usr/bin/curl >/dev/null 2>&1; then
    /bin/bash -c "$(/usr/bin/curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  else
    echo "System curl not found. Cannot install Homebrew automatically."
    echo "Please install Homebrew manually from https://brew.sh"
    exit 1
  fi
  
  # Add Homebrew to PATH for current session
  if [ -d "/opt/homebrew/bin" ]; then
    export PATH="/opt/homebrew/bin:$PATH"
  elif [ -d "/usr/local/bin" ]; then
    export PATH="/usr/local/bin:$PATH"
  fi
  
  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew installation failed or not on PATH"
    exit 1
  fi
  
  echo "Homebrew installed successfully"
}

# ============================================================================
# PHASE 2: Core Utilities (curl/wget)
# ============================================================================

install_curl_if_needed() {
  set_fetch && return 0
  if [ "$INSTALL_MODE" != "1" ]; then
    echo "curl/wget not found. Re-run with --fix or INSTALL_DEPS=1, or install curl manually."
    exit 1
  fi
  echo "Installing curl..."
  case "$OS_TYPE" in
    macos)
      if ! command -v brew >/dev/null 2>&1; then
        echo "ERROR: Homebrew not found. Cannot install curl."
        exit 1
      fi
      brew install curl
      ;;
    linux|wsl)
      if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update -y && sudo apt-get install -y curl
      elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y curl
      elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm curl
      else
        echo "Please install curl using your distro's package manager."; exit 1
      fi
      ;;
    git-bash)
      if ! command -v choco >/dev/null 2>&1; then
        echo "ERROR: Chocolatey not found. Cannot install curl."
        exit 1
      fi
      choco install -y curl
      ;;
  esac
  set_fetch || { echo "curl installation failed or not on PATH"; exit 1; }
}

# ============================================================================
# PHASE 3: Python Installation
# ============================================================================

# Python check and installation
install_python_if_needed() {
  if command -v python3 >/dev/null 2>&1; then
    debug_log "Python3 already installed: $(python3 --version 2>&1)"
    return 0
  fi
  
  if [ "$INSTALL_MODE" != "1" ]; then
    echo "Python3 not found. Re-run with --fix or INSTALL_DEPS=1 to install automatically."
    exit 1
  fi
  
  echo "Python3 not found. Installing..."
  case "$OS_TYPE" in
    macos)
      if ! command -v brew >/dev/null 2>&1; then
        echo "ERROR: Homebrew not found. Cannot install Python3."
        exit 1
      fi
      echo "Installing Python3 via Homebrew..."
      brew install python3
      ;;
    linux)
      if command -v apt-get >/dev/null 2>&1; then
        echo "Installing Python3 via apt..."
        sudo apt-get update -y && sudo apt-get install -y python3 python3-pip python3-venv
      elif command -v dnf >/dev/null 2>&1; then
        echo "Installing Python3 via dnf..."
        sudo dnf install -y python3 python3-pip
      elif command -v pacman >/dev/null 2>&1; then
        echo "Installing Python3 via pacman..."
        sudo pacman -Sy --noconfirm python python-pip
      else
        echo "Unsupported package manager. Please install Python3 manually."
        exit 1
      fi
      ;;
    wsl)
      echo "Installing Python3 via apt (WSL)..."
      sudo apt-get update -y && sudo apt-get install -y python3 python3-pip python3-venv
      ;;
    git-bash)
      if ! command -v choco >/dev/null 2>&1; then
        echo "ERROR: Chocolatey not found. Cannot install Python3."
        exit 1
      fi
      echo "Installing Python3 via Chocolatey..."
      choco install -y python3
      # Refresh PATH for current session
      export PATH="$PATH:/c/Python311:/c/Python311/Scripts:/c/Python310:/c/Python310/Scripts:/c/Python312:/c/Python312/Scripts"
      ;;
  esac
  
  # Verify installation
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Python3 installation failed or not on PATH"
    echo "You may need to restart your terminal/shell for PATH changes to take effect."
    exit 1
  fi
  
  echo "Python3 installed: $(python3 --version 2>&1)"
}

# ============================================================================
# MAIN INSTALLATION SEQUENCE
# ============================================================================

# Check cache FIRST before doing any installations
if check_dependencies_cached; then
  # Cache is valid and Docker daemon is running
  # Still need to verify compose works
  if ensure_compose; then
    debug_log "Dependencies already validated (cached)"
    exit 0
  else
    debug_log "Cache valid but compose not available, proceeding with checks"
  fi
fi

echo "Checking dependencies on $OS_TYPE (CLI-only mode)..."

# PHASE 1: Install package managers first
case "$OS_TYPE" in
  macos)
    install_homebrew_if_needed
    ;;
  git-bash)
    install_chocolatey_if_needed
    ;;
esac

# PHASE 2: Install curl/wget (needed for downloads)
set_fetch || install_curl_if_needed

# PHASE 3: Install Python (needed for various scripts)
install_python_if_needed

# PHASE 4: Check Docker and related tools

# Docker CLI
if ! command -v docker >/dev/null 2>&1; then
  if [ "$INSTALL_MODE" != "1" ]; then
    echo "Docker CLI not found. Re-run with --fix or INSTALL_DEPS=1 to install automatically."; exit 1
  fi
  echo "Docker CLI not found. Installing..."
  case "$OS_TYPE" in
    macos)
      if ! command -v brew >/dev/null 2>&1; then
        echo "ERROR: Homebrew not found. Cannot install Docker."
        exit 1
      fi
      echo "Installing Docker CLI and Colima (Docker Desktop alternative)..."
      brew install docker docker-compose docker-buildx colima
      echo "Configuring Docker CLI plugins..."
      mkdir -p ~/.docker
      if command -v jq >/dev/null 2>&1; then
        jq --null-input --arg dir "/opt/homebrew/lib/docker/cli-plugins" '{ cliPluginsExtraDirs: [$dir] }' > ~/.docker/config.json 2>/dev/null || true
      else
        brew install jq 2>/dev/null || true
        echo '{"cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]}' > ~/.docker/config.json
      fi
      ;;
    linux)
      echo "Installing Docker..."
      download_to "/tmp/get-docker.sh" "https://get.docker.com"
      sudo sh /tmp/get-docker.sh
      sudo usermod -aG docker "$USER"
      echo "Installing Docker Buildx..."
      BUILDX_VERSION="v0.12.0"
      mkdir -p ~/.docker/cli-plugins
      arch="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
      download_to ~/.docker/cli-plugins/docker-buildx "https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/buildx-${BUILDX_VERSION}.linux-${arch}"
      chmod +x ~/.docker/cli-plugins/docker-buildx
      echo "Please log out and back in for group changes to take effect"
      ;;
    wsl)
      echo "Installing Docker in WSL..."
      download_to "/tmp/get-docker.sh" "https://get.docker.com"
      sudo sh /tmp/get-docker.sh
      sudo usermod -aG docker "$USER"
      BUILDX_VERSION="v0.12.0"
      mkdir -p ~/.docker/cli-plugins
      arch="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
      download_to ~/.docker/cli-plugins/docker-buildx "https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/buildx-${BUILDX_VERSION}.linux-${arch}"
      chmod +x ~/.docker/cli-plugins/docker-buildx
      sudo service docker start || true
      ;;
    git-bash)
      echo "Detected Git Bash on Windows. Checking Docker via Windows PATH..."
      if cmd.exe /c "docker --version" 2>/dev/null | grep -q "Docker"; then
        echo "Docker found via Windows."
        export DOCKER_HOST="npipe:////./pipe/docker_engine"
      else
        echo "Docker not found. Installing Docker Desktop for Windows..."
        echo "Installing Docker Desktop via Chocolatey..."
        choco install -y docker-desktop
        echo "Please log out and log back in, or restart your computer for Docker Desktop to work properly."
        echo "After restart, Docker Desktop should start automatically."
        exit 1
      fi
      ;;
  esac
fi

# Compose
if ! ensure_compose; then
  if [ "$INSTALL_MODE" != "1" ]; then
    echo "docker-compose not found. Re-run with --fix or INSTALL_DEPS=1 to install automatically."; exit 1
  fi
  echo "Installing docker-compose..."
  case "$OS_TYPE" in
    macos)
      if command -v brew >/dev/null 2>&1; then
        pkill -f docker-compose 2>/dev/null || true
        rm -rf ~/Library/Caches/Homebrew/docker-compose* 2>/dev/null || true
        HOMEBREW_NO_AUTO_UPDATE=1 brew fetch -v docker-compose 2>/dev/null || true
        HOMEBREW_NO_AUTO_UPDATE=1 brew install -v docker-compose
        mkdir -p ~/.docker
        if command -v jq >/dev/null 2>&1; then
          jq --null-input --arg dir "/opt/homebrew/lib/docker/cli-plugins" '{ cliPluginsExtraDirs: [$dir] }' > ~/.docker/config.json 2>/dev/null || true
        else
          echo '{"cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]}' > ~/.docker/config.json
        fi
      else
        download_to /tmp/docker-compose "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-Darwin-$(uname -m)"
        chmod +x /tmp/docker-compose
        sudo mv /tmp/docker-compose /usr/local/bin/docker-compose
      fi
      ;;
    linux|wsl)
      download_to /tmp/docker-compose "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-Linux-$(uname -m)"
      sudo mv /tmp/docker-compose /usr/local/bin/docker-compose
      sudo chmod +x /usr/local/bin/docker-compose
      ;;
    git-bash)
      # Docker Desktop for Windows includes docker compose
      if docker compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE_CMD="docker compose"
      else
        echo "docker-compose not found. Ensure Docker Desktop is installed and running."
        echo "If Docker Desktop is not installed, install it via: choco install docker-desktop"
        exit 1
      fi
      ;;
  esac
  ensure_compose || { echo "Failed to install docker-compose"; exit 1; }
fi

# Ensure Docker daemon
if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not running. Starting..."
  case "$OS_TYPE" in
    macos)
      if ! command -v colima >/dev/null 2>&1; then
        if [ "$INSTALL_MODE" = "1" ]; then
          echo "Installing Colima..."
          brew install colima
        else
          echo "Colima not found. Re-run with --fix or INSTALL_DEPS=1 to install automatically."; exit 1
        fi
      fi
      echo "Starting Colima..."
      if colima status >/dev/null 2>&1; then
        colima start 2>/dev/null || colima start
      else
        colima start --cpu 2 --memory 4 --disk 20 2>/dev/null || colima start
      fi
      ;;
    linux|wsl)
      sudo systemctl start docker 2>/dev/null || sudo service docker start 2>/dev/null || {
        echo "Starting dockerd directly..."
        sudo dockerd >/dev/null 2>&1 &
      }
      ;;
    git-bash)
      echo "Start Docker Desktop or Rancher Desktop, then press Enter to continue..."
      read -r _
      ;;
  esac
  echo "Waiting for Docker to start (up to 30s)..."
  for i in {1..30}; do
    docker info >/dev/null 2>&1 && break
    sleep 1; echo -n "."
  done
  echo ""
  docker info >/dev/null 2>&1 || { echo "Docker failed to start."; exit 1; }
fi

mark_dependencies_checked
echo "All dependencies satisfied."
