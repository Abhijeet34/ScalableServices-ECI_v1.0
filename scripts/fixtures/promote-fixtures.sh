#!/bin/bash
# Promote latest exported fixtures into seed data directory after confirmation
# Shows diffs before applying. Supports --dry-run and --yes flags.
set -euo pipefail

SEED_DIR="services/seed/eci_seed_data"
EXPORTS_ROOT="services/seed/exports"
APPLY=0
DRY_RUN=0
SOURCE_DIR=""

usage() {
  echo "Usage: $0 [--yes] [--dry-run] [--source <export_dir>]"
}

# Parse args
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) APPLY=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --source) SOURCE_DIR="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [ -z "$SOURCE_DIR" ]; then
  if [ ! -d "$EXPORTS_ROOT" ]; then
    echo "No exports found at $EXPORTS_ROOT" >&2
    exit 2
  fi
  SOURCE_DIR=$(ls -1dt "$EXPORTS_ROOT"/* 2>/dev/null | head -n 1 || true)
  if [ -z "$SOURCE_DIR" ]; then
    echo "No export directories found in $EXPORTS_ROOT" >&2
    exit 2
  fi
fi

if [ ! -d "$SOURCE_DIR" ]; then
  echo "Source export directory not found: $SOURCE_DIR" >&2
  exit 2
fi

mkdir -p "$SEED_DIR"

echo "Promoting fixtures from: $SOURCE_DIR"
echo "Seed target directory: $SEED_DIR"

# Diff helper with color if available (delta > git diff > colordiff > diff)
show_diff() {
  local a="$1" b="$2"
  if command -v delta >/dev/null 2>&1 && command -v git >/dev/null 2>&1; then
    git --no-pager diff --no-index --color=always "$a" "$b" | delta
  elif command -v git >/dev/null 2>&1; then
    git --no-pager diff --no-index --color=always "$a" "$b"
  elif command -v colordiff >/dev/null 2>&1; then
    colordiff -u "$a" "$b"
  else
    diff -u "$a" "$b"
  fi
}

CHANGED=()
ADDED=()
for f in "$SOURCE_DIR"/eci_*.csv; do
  base=$(basename "$f")
  target="$SEED_DIR/$base"
  if [ -f "$target" ]; then
    if ! diff -q "$target" "$f" >/dev/null 2>&1; then
      CHANGED+=("$base")
    fi
  else
    ADDED+=("$base")
  fi
done

if [ ${#CHANGED[@]} -eq 0 ] && [ ${#ADDED[@]} -eq 0 ]; then
  echo "No differences detected. Seed data is up to date."
  exit 0
fi

printf "\nPlanned changes:\n"
[ ${#CHANGED[@]} -gt 0 ] && printf "  Modified: %s\n" "${CHANGED[*]}"
[ ${#ADDED[@]} -gt 0 ] && printf "  Added:    %s\n" "${ADDED[*]}"

printf "\nDiff preview (unified):\n"
if [ ${#CHANGED[@]} -gt 0 ]; then
  for base in "${CHANGED[@]}"; do
    printf "\n=== %s ===\n" "$base"
    show_diff "$SEED_DIR/$base" "$SOURCE_DIR/$base" || true
  done
fi
if [ ${#ADDED[@]} -gt 0 ]; then
  for base in "${ADDED[@]}"; do
    printf "\n=== %s (new) ===\n" "$base"
    head -n 5 "$SOURCE_DIR/$base" || true
    printf "...\n"
  done
fi

if [ "$DRY_RUN" -eq 1 ]; then
  printf "\nDry run: no changes applied.\n"
  exit 0
fi

cat <<WARN

WARNING: You are about to overwrite seed CSVs in $SEED_DIR.
This affects reseed baselines for dev/QA/CI. Review diffs above carefully.
Type 'yes' to proceed: 
WARN

if [ "$APPLY" -ne 1 ]; then
  read -r confirm
  if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 1
  fi
fi

# Apply copies
for f in "$SOURCE_DIR"/eci_*.csv; do
  cp -f "$f" "$SEED_DIR/"
  echo "Updated $(basename "$f")"
done

printf "\nPromotion complete. Consider committing changes to version control.\n"
