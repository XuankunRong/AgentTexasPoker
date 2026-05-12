#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export CONFIG_PATH="${CONFIG_PATH:-$ROOT_DIR/configs/deepseek/6deepseek_10bb_ss500.json}"
exec "$ROOT_DIR/scripts/run_simulation.sh" "$@"
