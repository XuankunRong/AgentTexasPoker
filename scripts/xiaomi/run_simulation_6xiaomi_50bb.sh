#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export CONFIG_PATH="${CONFIG_PATH:-$ROOT_DIR/configs/xiaomi/6xiaomi_50bb.json}"
exec "$ROOT_DIR/scripts/run_simulation.sh" "$@"
