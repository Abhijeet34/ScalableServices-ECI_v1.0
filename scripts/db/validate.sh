#!/bin/bash
set -e
source "$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)/lib/common.sh"

ensure_compose || { echo "docker-compose not found"; exit 1; }

echo "Validating database integrity..."
VIOLATIONS=$($DOCKER_COMPOSE_CMD exec -T postgres psql -U eci -d eci -t -c "\
  SELECT COUNT(*) FROM payments p WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.order_id = p.order_id);\
" 2>/dev/null | tr -d ' ' || echo "0")
if [ "$VIOLATIONS" -gt 0 ]; then
  echo "Found $VIOLATIONS orphaned payment records. Cleaning..."
  $DOCKER_COMPOSE_CMD exec -T postgres psql -U eci -d eci -c "\
    DELETE FROM payments p WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.order_id = p.order_id);\
  " >/dev/null 2>&1
  echo "Database cleaned."
fi

VIOLATIONS=$($DOCKER_COMPOSE_CMD exec -T postgres psql -U eci -d eci -t -c "\
  SELECT COUNT(*) FROM shipments s WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.order_id = s.order_id);\
" 2>/dev/null | tr -d ' ' || echo "0")
if [ "$VIOLATIONS" -gt 0 ]; then
  echo "Found $VIOLATIONS orphaned shipment records. Cleaning..."
  $DOCKER_COMPOSE_CMD exec -T postgres psql -U eci -d eci -c "\
    DELETE FROM shipments s WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.order_id = s.order_id);\
  " >/dev/null 2>&1
  echo "Database cleaned."
fi

echo "Database validation complete."
