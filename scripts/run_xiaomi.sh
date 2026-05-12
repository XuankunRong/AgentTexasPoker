#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
usage() {
  cat <<'USAGE'
Usage: scripts/run_xiaomi.sh <variant> [extra args]

Variants:
  10bb 50bb 100bb 200bb 10bb_ss100 10bb_ss500

Environment:
  export XIAOMI_API_KEY='your-key'
  export RUN_NAME='optional-run-name'
  export MAX_HANDS=500
  export RESUME_RUN_DIR='/absolute/path/to/run'   # optional
USAGE
}
case "${1:-}" in
  10bb) shift; exec "$ROOT_DIR/scripts/xiaomi/run_simulation_6xiaomi_10bb.sh" "$@" ;;
  50bb) shift; exec "$ROOT_DIR/scripts/xiaomi/run_simulation_6xiaomi_50bb.sh" "$@" ;;
  100bb) shift; exec "$ROOT_DIR/scripts/xiaomi/run_simulation_6xiaomi_100bb.sh" "$@" ;;
  200bb) shift; exec "$ROOT_DIR/scripts/xiaomi/run_simulation_6xiaomi_200bb.sh" "$@" ;;
  10bb_ss100) shift; exec "$ROOT_DIR/scripts/xiaomi/run_simulation_6xiaomi_10bb_ss100.sh" "$@" ;;
  10bb_ss500) shift; exec "$ROOT_DIR/scripts/xiaomi/run_simulation_6xiaomi_10bb_ss500.sh" "$@" ;;
  -h|--help|"") usage ;;
  *) echo "Unknown variant: $1" >&2; usage; exit 1 ;;
esac
