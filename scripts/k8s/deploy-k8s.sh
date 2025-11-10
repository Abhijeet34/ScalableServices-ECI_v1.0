#!/bin/bash
# Deploy ECI Platform to Kubernetes (k3d)
# Cross-platform deployment: macOS, Linux, Windows (WSL/Git Bash)
#
# Platform Support:
#   ✓ macOS     : Full auto-install (Homebrew or curl)
#   ✓ Linux     : Full auto-install (curl)
#   ✓ WSL/WSL2  : Full auto-install (detected as Linux)
#   ⚠ Windows   : Requires Chocolatey for auto-install (or WSL2 recommended)
#
# Requirements:
#   - Docker running (Colima, Docker Desktop, or Docker Engine)
#   - 4GB+ RAM available
#   - 2+ CPU cores

set -e

# Build settings: defaults (overridable)
: "${DOCKER_BUILDKIT:=1}"
: "${BUILDKIT_PROGRESS:=plain}"
export DOCKER_BUILDKIT BUILDKIT_PROGRESS
# Optimized build parallelism - allows more concurrent builds for faster deployment
: "${ECI_BUILD_JOBS:=6}"

# Detect interactive TTY and allow disabling screen clearing
if [ -t 0 ] && [ -t 1 ]; then
    INTERACTIVE=1
else
    INTERACTIVE=0
fi
# Set CLEAR_SCREEN=0 to disable menu clears (prevents blank lines in captured output)
CLEAR_SCREEN=${CLEAR_SCREEN:-1}

# Detect OS
detect_os() {
    case "$OSTYPE" in
        darwin*)  OS="macos" ;;
        linux*)   OS="linux" ;;
        msys*|cygwin*|win32) OS="windows" ;;
        *) echo "Unsupported OS: $OSTYPE"; exit 1 ;;
    esac
}

# Helper functions (cross-platform)
# Return newest mtime (epoch seconds) under a directory (recursively). Falls back to 0 if python3 is unavailable.
newest_mtime_epoch() {
    local dir="$1"
    if command -v python3 >/dev/null 2>&1; then
        python3 - "$dir" <<'PY'
import os, sys
root=sys.argv[1]
latest=0.0
for dp, dn, fn in os.walk(root or '.'):
    for f in fn:
        try:
            p=os.path.join(dp,f)
            m=os.path.getmtime(p)
            if m>latest:
                latest=m
        except Exception:
            pass
print(int(latest))
PY
    else
        echo 0
    fi
}

# Return Docker image Created time as epoch seconds. Falls back to 0 on error.
docker_image_created_epoch() {
    local image="$1"
    local created
    created=$(docker image inspect "$image" --format='{{.Created}}' 2>/dev/null | head -n1)
    if [ -z "$created" ]; then echo 0; return; fi
    if command -v python3 >/dev/null 2>&1; then
        python3 - "$created" <<'PY'
import sys, re, datetime
s=sys.argv[1].strip()
# Strip fractional seconds and Z
a=re.sub(r'\.\d+','',s).replace('Z','')
# Remove timezone offset if any (treat as UTC)
a=re.sub(r'[\+\-]\d{2}:?\d{2}$','',a)
# Parse as UTC
try:
    dt=datetime.datetime.strptime(a,'%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    print(int(dt.timestamp()))
except Exception:
    print(0)
PY
    else
        echo 0
    fi
}

# Check prerequisites
check_prerequisites() {
    echo "Checking prerequisites..."
    detect_os

    # Check Docker
    if ! docker info &> /dev/null; then
        echo "ERROR: Docker is not running."
        echo "Please start Docker or run: ./launcher.sh (auto-installs Docker runtime)"
        exit 1
    fi

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        echo "kubectl not found. Installing..."

        if [ "$OS" = "macos" ]; then
            if command -v brew &> /dev/null; then
                brew install kubectl
            else
                curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/darwin/amd64/kubectl"
                chmod +x kubectl && sudo mv kubectl /usr/local/bin/
            fi
        elif [ "$OS" = "linux" ]; then
            curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
            chmod +x kubectl && sudo mv kubectl /usr/local/bin/
        elif [ "$OS" = "windows" ]; then
            echo "kubectl not found. Attempting Windows installation..."
            
            # Try chocolatey first
            if command -v choco &> /dev/null; then
                echo "Installing kubectl via Chocolatey..."
                choco install kubernetes-cli -y
            else
                echo ""
                echo "Please install kubectl manually:"
                echo "  Option 1: Install Chocolatey, then run: choco install kubernetes-cli"
                echo "  Option 2: Download from: https://kubernetes.io/docs/tasks/tools/install-kubectl-windows/"
                echo "  Option 3: Use WSL2 for better compatibility: wsl --install"
                echo ""
                exit 1
            fi
        fi
    fi

    # Check k3d
    if ! command -v k3d &> /dev/null; then
        echo "k3d not found. Installing..."

        if [ "$OS" = "macos" ]; then
            if command -v brew &> /dev/null; then
                brew install k3d
            else
                curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
            fi
        elif [ "$OS" = "linux" ]; then
            curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
        elif [ "$OS" = "windows" ]; then
            echo "k3d not found. Attempting Windows installation..."
            
            # Try chocolatey first
            if command -v choco &> /dev/null; then
                echo "Installing k3d via Chocolatey..."
                choco install k3d -y
            else
                echo ""
                echo "Please install k3d manually:"
                echo "  Option 1: Install Chocolatey, then run: choco install k3d"
                echo "  Option 2: Download from: https://k3d.io/#installation"
                echo "  Option 3 (RECOMMENDED): Use WSL2 for full compatibility"
                echo "    - Open PowerShell as Admin"
                echo "    - Run: wsl --install -d Ubuntu"
                echo "    - Restart and run this script in WSL"
                echo ""
                exit 1
            fi
        fi
    fi

    echo "✓ All prerequisites installed"
}

# Start k3d cluster
start_k3d() {
    echo "Starting k3d cluster..."

    if k3d cluster list | grep -q "eci-cluster"; then
        echo "✓ Cluster 'eci-cluster' already exists"
    else
        echo "Creating new k3d cluster (takes ~30 seconds)..."
        k3d cluster create eci-cluster \
            --servers 1 \
            --agents 0 \
            --port "30080:30080@server:0" \
            --port "30008:30008@server:0" \
            --k3s-arg "--disable=traefik@server:0" \
            --wait
        echo "✓ Cluster created successfully"
    fi
}

# Build Docker images and import to k3d
build_images() {
    echo "Building Docker images..."
    
    # Enable BuildKit for faster builds with inline caching
    export DOCKER_BUILDKIT=1
    export COMPOSE_DOCKER_CLI_BUILD=1
    export BUILDKIT_PROGRESS=plain  # Cleaner build output

    # Check which images need rebuilding
    local SERVICES="customers products inventory orders payments shipments gateway dashboard seed"
    local TO_BUILD=()
    
    echo "Checking existing images..."
    for service in $SERVICES; do
        # Always rebuild seed image (contains data files that may change)
        # Always rebuild dashboard to ensure UI/template changes are picked up
        if [ "$service" = "seed" ] || [ "$service" = "dashboard" ]; then
            TO_BUILD+=("$service")
            echo "  ! $service: rebuilding (forced)"
        elif ! docker image inspect eci/$service:latest >/dev/null 2>&1; then
            TO_BUILD+=("$service")
            echo "  ! $service: image missing (will build)"
        else
            # Compare source mtime vs image creation time (cross-platform via python3)
            local src_epoch=$(newest_mtime_epoch "./services/$service")
            local img_epoch=$(docker_image_created_epoch "eci/$service:latest")
            local now_ts=$(date +%s)
            local age_hours=0
            if [ "$img_epoch" -gt 0 ]; then
                age_hours=$(( (now_ts - img_epoch) / 3600 ))
            fi

            if [ "$src_epoch" -gt 0 ] && [ "$img_epoch" -gt 0 ] && [ "$src_epoch" -gt "$img_epoch" ]; then
                TO_BUILD+=("$service")
                echo "  ! $service: source changed since last image (will rebuild)"
            elif [ "$img_epoch" -gt 0 ] && [ $age_hours -gt 24 ]; then
                TO_BUILD+=("$service")
                echo "  ! $service: image is ${age_hours}h old (rebuilding for freshness)"
            else
                echo "  ✓ $service: image exists (skipping)"
            fi
        fi
    done
    
    if [ ${#TO_BUILD[@]} -eq 0 ]; then
        echo "✓ All images already built. Use 'delete' and redeploy to rebuild."
    else
        echo "Building ${#TO_BUILD[@]} images (max ${ECI_BUILD_JOBS:-6} parallel jobs)..."
        
        # Optimized parallelism for faster builds (6 concurrent jobs)
        local MAX_PARALLEL=${ECI_BUILD_JOBS:-6}
        local pids=()
        
        # Optional no-cache mode (set ECI_NO_CACHE=1 to force)
        local NO_CACHE_FLAG=""
        if [ "${ECI_NO_CACHE:-0}" = "1" ]; then
            NO_CACHE_FLAG="--no-cache"
        fi
        
        for service in "${TO_BUILD[@]}"; do
            (
                echo "  Building $service..."
                # Optimized build with inline cache and compression
                if docker build -q -t eci/$service:latest \
                    ${NO_CACHE_FLAG} \
                    --build-arg BUILDKIT_INLINE_CACHE=1 \
                    --build-arg RELEASE_ID=$(git --no-pager rev-parse --short=12 HEAD 2>/dev/null || echo dev) \
                    -f ./services/$service/Dockerfile . > /tmp/build_$service.log 2>&1; then
                    echo "  ✓ $service built successfully"
                else
                    echo "  ✗ $service build failed"
                    echo "$service" >> /tmp/build_failures.txt
                fi
            ) &
            pids+=($!)
            
            # Wait if we hit max parallel
            if [ ${#pids[@]} -ge $MAX_PARALLEL ]; then
                wait ${pids[0]}
                pids=("${pids[@]:1}")
            fi
        done
        
        # Wait for remaining builds
        wait
        
        # Check for failures
        if [ -f "/tmp/build_failures.txt" ]; then
            echo ""
            echo "Build failures:"
            while read -r service; do
                echo ""
                echo "=== $service build log ==="
                cat "/tmp/build_$service.log"
            done < /tmp/build_failures.txt
            rm -f /tmp/build_failures.txt /tmp/build_*.log
            exit 1
        fi
        
        rm -f /tmp/build_*.log
        echo "✓ All images built successfully!"
    fi
    
    # Import images to k3d cluster (only those missing or rebuilt)
    echo ""
    echo "Preparing image import list..."

    # Find k3d server node name (robust to naming differences)
    local K3D_NODE
    K3D_NODE=$(docker ps --filter "name=k3d-eci-cluster-server" --format '{{.Names}}' | head -n1)

    local TO_IMPORT=()
    
    # Get all cluster images in one call (much faster)
    local CLUSTER_IMAGES=""
    if [ -n "$K3D_NODE" ]; then
        CLUSTER_IMAGES=$(docker exec "$K3D_NODE" sh -c "ctr -n k8s.io images list -q 2>/dev/null" 2>/dev/null || echo "")
    fi

    for service in $SERVICES; do
        local needs_import=0

        # If built in this run, import
        for built in "${TO_BUILD[@]}"; do
            if [ "$built" = "$service" ]; then
                needs_import=1
                break
            fi
        done

        # If not built now, check if image exists inside the k3d cluster (using cached list)
        if [ $needs_import -eq 0 ]; then
            if echo "$CLUSTER_IMAGES" | grep -q "eci/$service:latest"; then
                echo "  ✓ $service: image already present in cluster (skip import)"
            else
                needs_import=1
            fi
        fi

        if [ $needs_import -eq 1 ]; then
            TO_IMPORT+=("eci/$service:latest")
        fi
    done

    if [ ${#TO_IMPORT[@]} -eq 0 ]; then
        echo "✓ All images already present in cluster; skipping import"
    else
        echo "Importing ${#TO_IMPORT[@]} image(s) to k3d cluster..."
        # Optimized import: larger batches for faster processing
        # k3d can efficiently handle 5-6 images at once
        if [ ${#TO_IMPORT[@]} -le 6 ]; then
            # Small to medium batch: import all at once
            k3d image import -c eci-cluster --verbose=false "${TO_IMPORT[@]}" 2>&1 | grep -v '^$' | head -n 3 || true
        else
            # Large batch: use larger chunks (5 instead of 3) for faster import
            local CHUNK_SIZE=5
            local total=${#TO_IMPORT[@]}
            for ((i=0; i<total; i+=CHUNK_SIZE)); do
                local chunk=("${TO_IMPORT[@]:i:CHUNK_SIZE}")
                local progress=$((i+${#chunk[@]}))
                echo "  Progress: $progress/$total images..."
                k3d image import -c eci-cluster --verbose=false "${chunk[@]}" >/dev/null 2>&1
            done
        fi
        echo "✓ Images imported to cluster"
    fi
}

# Deploy to Kubernetes
deploy_services() {
    echo ""
    echo "Deploying services to Kubernetes..."

    # Apply all manifests in order
    echo "Applying Kubernetes manifests..."
    kubectl apply -f k8s/postgres-deployment.yaml >/dev/null
    kubectl apply -f k8s/redis-deployment.yaml >/dev/null
    kubectl apply -f k8s/services-deployment.yaml >/dev/null
    echo "✓ Manifests applied"

    # Ensure dashboard picks up latest image when rebuilt
    echo "Rolling out dashboard to pick up latest image..."
    kubectl -n eci-platform rollout restart deployment/dashboard >/dev/null 2>&1 || true

    # Wait for infrastructure services first (reduced timeout with faster probes)
    echo ""
    echo "Waiting for infrastructure services..."
    kubectl wait --namespace=eci-platform \
        --for=condition=available \
        --timeout=60s \
        deployment/postgres deployment/redis 2>/dev/null || {
            echo "Infrastructure services failed. Checking status:"
            kubectl get pods -n eci-platform
            exit 1
        }
    echo "✓ PostgreSQL and Redis ready"
    
    # Wait for application services (faster with optimized probes)
    echo ""
    echo "Waiting for application services..."
    echo "(This takes ~15-30s with optimized health checks)"
    
    # Try waiting for all deployments with reduced timeout (60s instead of 90s)
    if ! kubectl wait --namespace=eci-platform \
        --for=condition=available \
        --timeout=60s \
        deployment --all 2>/dev/null; then
        
        echo ""
        echo "Some services need troubleshooting..."
        
        # Auto-fix: Restart failed pods to pick up correct env vars
        echo "Restarting failed/error pods..."
        local FAILED_PODS=$(kubectl get pods -n eci-platform --field-selector=status.phase!=Running,status.phase!=Succeeded -o jsonpath='{.items[*].metadata.labels.app}' 2>/dev/null)
        
        if [ -n "$FAILED_PODS" ]; then
            for app in $FAILED_PODS; do
                echo "  Restarting $app pods..."
                kubectl delete pod -n eci-platform -l app=$app --ignore-not-found=true 2>/dev/null
            done
            
            echo ""
            echo "Waiting for restarted pods (20s)..."
            sleep 20
        fi
        
        # Show current status
        echo ""
        echo "Current status:"
        kubectl get pods -n eci-platform
        
        # Check if critical services are running
        local RUNNING=$(kubectl get pods -n eci-platform --field-selector=status.phase=Running -o name 2>/dev/null | wc -l)
        if [ "$RUNNING" -ge 7 ]; then
            echo ""
            echo "⚠ Core microservices are running (${RUNNING} pods)"
            echo "Some services may need additional troubleshooting."
            echo "Check logs: kubectl logs -n eci-platform deployment/<service-name>"
        else
            echo ""
            echo "✗ Deployment failed. Check logs:"
            echo "  kubectl logs -n eci-platform deployment/<service-name>"
            exit 1
        fi
    else
        echo "✓ All services ready"
    fi
    
    # Seed initial data
    echo ""
    echo "Loading seed data..."
    kubectl delete job seed-data -n eci-platform 2>/dev/null || true
    sleep 1
    kubectl apply -f k8s/seed-job.yaml >/dev/null
    
    # Reduced timeout from 45s to 30s - seed job should complete quickly
    if kubectl wait --namespace=eci-platform --for=condition=complete --timeout=30s job/seed-data 2>/dev/null; then
        echo "✓ Seed data loaded"
    else
        echo "Seed job still running. Check with:"
        echo "  kubectl logs -n eci-platform job/seed-data -f"
    fi
    
    echo ""
    echo "✓ All services deployed successfully!"
}

# Show status
show_status() {
    echo ""
    echo "=========================================================="
    echo "Deployment Status"
    echo "=========================================================="
    
    echo ""
    echo "Pods:"
    kubectl get pods -n eci-platform
    
    echo ""
    echo "Services:"
    kubectl get svc -n eci-platform

    echo ""
    echo "=========================================================="
    echo "Access URLs"
    echo "=========================================================="
    echo "Gateway API    : http://localhost:30080"
    echo "Swagger UI     : http://localhost:30080/swagger"
    echo "GraphQL        : http://localhost:30080/graphql"
    echo "Dashboard      : http://localhost:30008"

    echo ""
    echo "=========================================================="
    echo "Useful Commands"
    echo "=========================================================="
    echo "View logs      : kubectl logs -n eci-platform deployment/<service-name> -f"
    echo "Check pods     : kubectl get pods -n eci-platform"
    echo "Shell into pod : kubectl exec -n eci-platform -it deployment/<service-name> -- /bin/sh"
    echo "Delete cluster : k3d cluster delete eci-cluster"
    echo "Stop cluster   : k3d cluster stop eci-cluster"
    echo "Start cluster  : k3d cluster start eci-cluster"
    echo ""
}

# Main deployment
deploy_full() {
    local start_time=$(date +%s)
    
    check_prerequisites
    start_k3d
    build_images
    deploy_services
    show_status
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    echo ""
    echo "Total deployment time: ${duration}s"
}

# Reseed database in k8s
reseed_k8s() {
    echo "Reseeding Kubernetes database..."
    echo "This will drop schema, run migrations, and then reload seed data."
    
    # Ensure postgres pod is ready (reduced timeout from 90s to 30s)
    kubectl wait --namespace=eci-platform --for=condition=ready --timeout=30s pod -l app=postgres 2>/dev/null || true
    POSTGRES_POD=$(kubectl get pods -n eci-platform -l app=postgres -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -n "$POSTGRES_POD" ]; then
        echo "Dropping and recreating schema in Postgres..."
        kubectl exec -n eci-platform "$POSTGRES_POD" -- psql -U eci -d eci -c "\
          DROP SCHEMA public CASCADE;\
          CREATE SCHEMA public;\
          GRANT ALL ON SCHEMA public TO eci;\
          GRANT ALL ON SCHEMA public TO public;\
        " >/dev/null 2>&1 || echo "Warning: could not drop schema (db may be initializing)"
    fi

    # Run migrations in each service pod if available
    for svc in customers products inventory orders payments shipments; do
        POD=$(kubectl get pods -n eci-platform -l app=$svc -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
        if [ -n "$POD" ]; then
            kubectl exec -n eci-platform "$POD" -- alembic upgrade head >/dev/null 2>&1 || true
            echo "  - $svc: migrations attempted"
        fi
    done
    
    # Delete any existing seed job
    kubectl delete job seed-data -n eci-platform 2>/dev/null || true
    sleep 1
    
    # Run new seed job
    echo "Loading seed data..."
    kubectl apply -f k8s/seed-job.yaml >/dev/null
    
    # Reduced timeout from 120s to 60s for faster feedback
    if kubectl wait --namespace=eci-platform --for=condition=complete --timeout=60s job/seed-data 2>/dev/null; then
        echo "✓ Seed data loaded successfully!"
    else
        echo "Seed job is running. Check with:"
        echo "  kubectl logs -n eci-platform job/seed-data -f"
    fi
}

# Fix failed pods
fix_pods() {
    echo "Attempting to fix failed pods..."
    
    # Restart failed/error pods
    FAILED_PODS=$(kubectl get pods -n eci-platform --field-selector=status.phase!=Running,status.phase!=Succeeded -o jsonpath='{.items[*].metadata.labels.app}' 2>/dev/null)
    
    if [ -z "$FAILED_PODS" ]; then
        echo "✓ No failed pods found"
    else
        echo "Restarting failed pods: $FAILED_PODS"
        for app in $FAILED_PODS; do
            kubectl delete pod -n eci-platform -l app=$app 2>/dev/null
        done
        echo ""
        echo "Waiting 20s for pods to restart..."
        sleep 20
        kubectl get pods -n eci-platform
    fi
}

# Build diagnostics for Docker/BuildKit
build_diagnostics() {
    echo "Build diagnostics (Docker BuildKit / cache usage):"
    echo ""
    echo "Buildx builders:"
    docker buildx ls || true
    echo ""
    echo "BuildKit containers:"
    docker ps --filter "name=buildkit" --format "table {{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Names}}" || true
    echo ""
    echo "Docker disk usage (images/containers/cache):"
    docker system df -v || true
    echo ""
    echo "Tip: If builds seem stuck, try: docker buildx prune -af"
}

# Rebuild all
rebuild_all() {
    echo "Rebuilding and redeploying..."
    echo "This will delete all images and redeploy."
    echo -n "Continue? (y/n): "
    read -r RESPONSE
    if [ "$RESPONSE" != "y" ] && [ "$RESPONSE" != "Y" ]; then
        echo "Rebuild cancelled."
        return
    fi

    # Optional: check for live/stuck builds before proceeding
    echo -n "Run build diagnostics (buildx, buildkit containers, disk usage)? (y/n): "
    read -r DIAG
    if [ "$DIAG" = "y" ] || [ "$DIAG" = "Y" ]; then
        build_diagnostics
    fi

    # Optional: prune BuildKit cache to clear stale layers
    echo -n "Prune Docker BuildKit cache before rebuild? (y/n): "
    read -r PRUNE
    if [ "$PRUNE" = "y" ] || [ "$PRUNE" = "Y" ]; then
        echo "Pruning BuildKit cache (this may take a while)..."
        docker buildx prune -af || true
        # Force no-cache builds for this run
        export ECI_NO_CACHE=1
        echo "✓ Build cache pruned; will rebuild without cache"
    else
        unset ECI_NO_CACHE
    fi
    
    # Delete images to force rebuild
    echo "Removing existing images..."
    docker rmi $(docker images 'eci/*' -q) 2>/dev/null || true
    
    # Delete namespace
    echo "Removing namespace..."
    kubectl delete namespace eci-platform 2>/dev/null || true
    sleep 3
    
    # Redeploy
    deploy_full
}

# View service logs
view_service_logs() {
    echo "Available services:"
    echo "  1) gateway"
    echo "  2) customers"
    echo "  3) products"
    echo "  4) inventory"
    echo "  5) orders"
    echo "  6) payments"
    echo "  7) shipments"
    echo "  8) dashboard"
    echo "  9) postgres"
    echo "  10) redis"
    echo ""
    echo -n "Select service (1-10): "
    read -r choice
    
    case $choice in
        1) service="gateway" ;;
        2) service="customers" ;;
        3) service="products" ;;
        4) service="inventory" ;;
        5) service="orders" ;;
        6) service="payments" ;;
        7) service="shipments" ;;
        8) service="dashboard" ;;
        9) service="postgres" ;;
        10) service="redis" ;;
        *) echo "Invalid choice"; return ;;
    esac
    
    echo "Showing logs for $service (press Ctrl+C to exit)..."
    kubectl logs -n eci-platform -f deployment/$service
}

# Test deployment
test_deployment() {
    echo "Testing k3d deployment..."
    echo ""
    
    # Check cluster
    if ! k3d cluster list | grep -q "eci-cluster"; then
        echo "✗ Cluster not found. Run deploy first."
        return
    fi
    echo "✓ Cluster exists"
    
    # Check pods
    RUNNING=$(kubectl get pods -n eci-platform --field-selector=status.phase=Running -o name 2>/dev/null | wc -l | tr -d ' ')
    TOTAL=$(kubectl get pods -n eci-platform -o name 2>/dev/null | wc -l | tr -d ' ')
    echo "✓ Pods: $RUNNING/$TOTAL running"
    
    # Test gateway endpoint
    echo ""
    echo "Testing gateway endpoint..."
    if curl -sf http://localhost:30080/docs >/dev/null 2>&1; then
        echo "✓ Gateway API responding"
    else
        echo "✗ Gateway not accessible yet"
    fi
    
    # Show URLs
    echo ""
    echo "Access URLs:"
    echo "  Gateway API: http://localhost:30080"
    echo "  Swagger UI:  http://localhost:30080/swagger"
    echo "  GraphQL:     http://localhost:30080/graphql"
    echo "  Dashboard:   http://localhost:30008"
}

# Stop cluster
stop_cluster() {
    echo "Stopping k3d cluster..."
    k3d cluster stop eci-cluster 2>/dev/null && \
        echo "✓ Cluster stopped (run 'Start Cluster' to resume)" || \
        echo "✗ Cluster not found or already stopped"
}

# Start cluster
start_cluster() {
    echo "Starting k3d cluster..."
    if k3d cluster start eci-cluster 2>/dev/null; then
        echo "✓ Cluster started"
        echo ""
        show_status
    else
        echo "✗ Cluster not found. Run 'Deploy Platform' first."
    fi
}

# Delete cluster
delete_cluster() {
    echo "WARNING: This will delete the entire k3d cluster and all data!"
    echo -n "Are you sure? (yes/no): "
    read -r confirmation
    if [ "$confirmation" = "yes" ]; then
        echo "Deleting k3d cluster..."
        k3d cluster delete eci-cluster >/dev/null 2>&1
        echo "✓ Cluster deleted"
    else
        echo "Deletion cancelled."
    fi
}

# Show interactive menu
show_menu() {
    echo "Cluster Management:"
    echo "  1) Deploy Platform"
    echo "  2) Show Status"
    echo "  3) Test Deployment"
    echo "  4) Start Cluster"
    echo "  5) Stop Cluster"
    echo "  6) Delete Cluster"
    echo ""
    echo "Service Management:"
    echo "  7) View Service Logs"
    echo "  8) Fix Failed Pods"
    echo "  9) Reseed Database"
    echo "  10) Rebuild All"
    echo ""
    echo "  0) Exit"
    echo "=========================================================="
    echo -n "Select option: "
}

# Interactive menu loop
interactive_menu() {
    echo "=========================================================="
    echo "ECI Platform - Kubernetes Deployment (k3d)"
    echo "Interactive Management Console"
    echo "=========================================================="
    
    # Check prerequisites once
    detect_os
    
    while true; do
        show_menu
        read -r option
        
        case $option in
            1)
                deploy_full
                ;;
            2)
                show_status
                ;;
            3)
                test_deployment
                ;;
            4)
                start_cluster
                ;;
            5)
                stop_cluster
                ;;
            6)
                delete_cluster
                ;;
            7)
                view_service_logs
                ;;
            8)
                fix_pods
                ;;
            9)
                reseed_k8s
                ;;
            10)
                rebuild_all
                ;;
            0)
                echo "Exiting..."
                exit 0
                ;;
            *)
                echo "Invalid option. Please try again."
                sleep 1
                ;;
        esac
        
        # Pause before showing menu again (except for exit)
        if [ "$option" != "0" ]; then
            if [ "$INTERACTIVE" -eq 1 ]; then
                # Drain any leftover input so the next prompt doesn't capture prior keystrokes
                # Use a non-blocking check (-t 0) for portability on macOS bash
                while IFS= read -r -t 0 -n 1 _; do :; done
                # Prompt without echoing typed keys to avoid stray characters like "10" showing
                read -r -n 1 -s -p "Press any key to continue..."
                # Clear screen (prefer tput if available) unless disabled
                if [ "$CLEAR_SCREEN" -eq 1 ]; then
                    if command -v tput >/dev/null 2>&1; then
                        tput clear
                    else
                        clear 2>/dev/null || printf '\033[2J\033[H'
                    fi
                else
                    echo ""
                    echo ""
                fi
            fi
        fi
    done
}

# Handle command-line arguments
if [ "$#" -eq 0 ]; then
    # No arguments - start interactive menu
    interactive_menu
else
    case "${1:-}" in
        deploy)
            deploy_full
            ;;
        delete)
            echo "Deleting k3d cluster..."
            k3d cluster delete eci-cluster
            echo "✓ Cluster deleted"
            ;;
        stop)
            stop_cluster
            ;;
        start)
            start_cluster
            ;;
        status)
            show_status
            ;;
        logs)
            if [ -z "${2:-}" ]; then
                echo "Usage: $0 logs <service-name>"
                echo "Available services: gateway customers products inventory orders payments shipments dashboard postgres redis"
                exit 1
            fi
            kubectl logs -n eci-platform -f deployment/$2
            ;;
        rebuild)
            rebuild_all
            ;;
        test)
            test_deployment
            ;;
        fix)
            fix_pods
            ;;
        reseed)
            reseed_k8s
            ;;
        help|--help|-h)
            echo "ECI Platform - Kubernetes Deployment (k3d)"
            echo ""
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  (none)    Start interactive menu (default)"
            echo "  deploy    Deploy full platform"
            echo "  status    Show deployment status and URLs"
            echo "  test      Test deployment and endpoints"
            echo "  logs      View logs for a service"
            echo "  fix       Restart failed pods"
            echo "  reseed    Reseed database"
            echo "  stop      Stop cluster (keeps data)"
            echo "  start     Start stopped cluster"
            echo "  rebuild   Force rebuild all images and redeploy"
            echo "  delete    Delete cluster completely"
            echo "  help      Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                  # Interactive menu"
            echo "  $0 deploy           # Deploy everything"
            echo "  $0 test             # Test deployment"
            echo "  $0 logs gateway     # View gateway logs"
            echo "  $0 fix              # Restart failed pods"
            echo "  $0 status           # Check deployment"
            ;;
        *)
            echo "Unknown command: $1"
            echo "Run '$0 help' for usage information"
            exit 1
            ;;
    esac
fi
