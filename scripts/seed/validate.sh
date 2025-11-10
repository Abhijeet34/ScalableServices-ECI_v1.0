#!/bin/bash
set -e
source "$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)/lib/common.sh"

echo "Validating seed data integrity..."
PAYMENTS_FILE="$ROOT_DIR/services/seed/eci_seed_data/eci_payments.csv"
SHIPMENTS_FILE="$ROOT_DIR/services/seed/eci_seed_data/eci_shipments.csv"
ORDERS_FILE="$ROOT_DIR/services/seed/eci_seed_data/eci_orders.csv"

[ ! -f "$ORDERS_FILE" ] && debug_log "Orders file not found, skipping validation" && exit 0

MAX_ORDER_ID=$(awk -F',' 'NR>1 {print $1}' "$ORDERS_FILE" | sort -n | tail -1)

auto_clean() {
  local file="$1" label="$2"
  [ -f "$file" ] || return 0
  INVALID=$(awk -F',' -v max="$MAX_ORDER_ID" 'NR>1 && ($2 < 1 || $2 > max) {print}' "$file" | wc -l | tr -d ' ')
  if [ "$INVALID" -gt 0 ]; then
    echo "Found $INVALID invalid $label entries. Cleaning..."
    awk -F',' -v max="$MAX_ORDER_ID" 'NR==1 || ($2 >= 1 && $2 <= max)' "$file" > "${file}.tmp"
    mv "${file}.tmp" "$file"
    echo "$label data cleaned."
  fi
}

auto_clean "$PAYMENTS_FILE" "payment"
auto_clean "$SHIPMENTS_FILE" "shipment"

echo "Seed data validation complete."
