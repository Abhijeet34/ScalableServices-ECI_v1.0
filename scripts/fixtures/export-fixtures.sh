#!/bin/bash
# Export curated fixtures from a PostgreSQL DB into CSV files
# Modes:
#   auto (default): detect compose/k8s/dburl automatically
#   --compose: exports from docker-compose postgres service
#   --k8s <namespace> <pod>: exports from a pod via kubectl exec
#   --dburl <DATABASE_URL>: exports using local psql against the given URL
# Output: services/seed/exports/<UTC_TIMESTAMP>/eci_*.csv
set -euo pipefail

usage() {
  echo "Usage: $0 [auto] | [--compose] | [--k8s <namespace> <pod>] | [--dburl <DATABASE_URL>]"
}

MODE=${1:-auto}
shift || true

OUT_DIR="services/seed/exports/$(date -u +%Y%m%d-%H%M%SZ)"
mkdir -p "$OUT_DIR"

TABLES=(customers products inventory orders order_items payments shipments)

# Resolve executors
COMPOSE_CMD=""
if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
else
  COMPOSE_CMD="docker-compose"
fi

run_copy() {
  local table="$1" out="$2"
  case "$MODE" in
    --compose)
      $COMPOSE_CMD exec -T postgres psql -U eci -d eci -c "COPY (SELECT * FROM ${table} ORDER BY 1) TO STDOUT WITH CSV HEADER" > "$out"
      ;;
    --k8s)
      local ns="${K8S_NS:-default}" pod="${K8S_POD:-}"
      if [ -z "$pod" ]; then echo "Missing pod name for --k8s" >&2; exit 2; fi
      kubectl exec -n "$ns" "$pod" -- psql -U eci -d eci -c "COPY (SELECT * FROM ${table} ORDER BY 1) TO STDOUT WITH CSV HEADER" > "$out"
      ;;
    --dburl)
      local url="${DATABASE_URL:-}"
      if [ -z "$url" ]; then echo "DATABASE_URL is required for --dburl" >&2; exit 2; fi
      # Requires local psql client
      psql "$url" -c "COPY (SELECT * FROM ${table} ORDER BY 1) TO STDOUT WITH CSV HEADER" > "$out"
      ;;
    *)
      usage; exit 2;
      ;;
  esac
}

# Interpret params / auto-detect
case "$MODE" in
  auto)
    # Prefer compose if postgres service is running
    if command -v docker >/dev/null 2>&1 && { docker compose version >/dev/null 2>&1 || docker-compose --version >/dev/null 2>&1; }; then
      if $COMPOSE_CMD ps postgres -q >/dev/null 2>&1 && [ -n "$($COMPOSE_CMD ps postgres -q 2>/dev/null)" ]; then
        MODE=--compose
      fi
    fi
    # If not compose, try k8s (look for a running pod with app=postgres)
    if [ "$MODE" = "auto" ] && command -v kubectl >/dev/null 2>&1; then
      read -r detected_ns detected_pod <<EOF || true
$(kubectl get pods --all-namespaces -l app=postgres -o jsonpath='{range .items[?(@.status.phase=="Running")]}{.metadata.namespace} {.metadata.name}{"\n"}{end}' | head -n 1)
EOF
      if [ -n "${detected_pod:-}" ]; then
        MODE=--k8s
        K8S_NS="$detected_ns"
        K8S_POD="$detected_pod"
      fi
    fi
    # Fall back to DATABASE_URL if set
    if [ "$MODE" = "auto" ] && [ -n "${DATABASE_URL:-}" ]; then
      MODE=--dburl
    fi
    # Final check
    if [ "$MODE" = "auto" ]; then
      echo "Could not auto-detect environment. Specify --compose, --k8s <ns> <pod>, or --dburl <DATABASE_URL>." >&2
      exit 2
    fi
    ;;
  --compose)
    ;;
  --k8s)
    K8S_NS="${1:-eci-platform}"
    K8S_POD="${2:-}"
    if [ -z "$K8S_POD" ]; then usage; echo "Example: $0 --k8s eci-platform $(kubectl get pods -n eci-platform -l app=postgres -o name | sed 's|pod/||')"; exit 2; fi
    ;;
  --dburl)
    export DATABASE_URL="${1:-}"
    if [ -z "$DATABASE_URL" ]; then usage; echo "Provide DATABASE_URL, e.g., postgres://eci:eci@localhost:5432/eci"; exit 2; fi
    ;;
  *)
    usage; exit 2;
    ;;
esac

echo "Exporting fixtures to $OUT_DIR (mode: $MODE)"
for t in "${TABLES[@]}"; do
  file="$OUT_DIR/eci_${t}.csv"
  echo "  - $t -> $(basename "$file")"
  run_copy "$t" "$file"
  if [ ! -s "$file" ]; then
    echo "    Warning: $file is empty"
  fi
done

echo "Export complete. Review files and, when ready, promote to services/seed/eci_seed_data/."
