#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DASHBOARD_ROOT="${DASHBOARD_ROOT:-$ROOT_DIR/outputs}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8765}"

cd "$ROOT_DIR"

echo "Project: $ROOT_DIR"
echo "Dashboard root: $DASHBOARD_ROOT"
echo "Web: http://127.0.0.1:$DASHBOARD_PORT"

python run_dashboard.py --root "$DASHBOARD_ROOT" --port "$DASHBOARD_PORT"
