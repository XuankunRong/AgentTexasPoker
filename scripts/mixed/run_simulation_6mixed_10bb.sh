#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export CONFIG_PATH="${CONFIG_PATH:-$ROOT_DIR/configs/mixed/6mixed_10bb.json}"
exec "$ROOT_DIR/scripts/run_simulation.sh" "$@"
