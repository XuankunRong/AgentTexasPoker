#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
usage() {
  cat <<'USAGE'
Usage: scripts/run_mixed.sh [extra args]

Environment:
  export SORUXGPT_API_KEY_CLAUDE='your-key'
  export SORUXGPT_API_KEY_GEMINI='your-key'
  export SORUXGPT_API_KEY_DEEPSEEK='your-key'
  export SORUXGPT_API_KEY_GPT='your-key'
  export QWEN_API_KEY='your-key'
  export XIAOMI_API_KEY='your-key'
  export RUN_NAME='optional-run-name'
  export MAX_HANDS=500
  export RESUME_RUN_DIR='/absolute/path/to/run'   # optional
USAGE
}
case "${1:-}" in
  -h|--help) usage ;;
  *) exec "$ROOT_DIR/scripts/mixed/run_simulation_6mixed_10bb.sh" "$@" ;;
esac
