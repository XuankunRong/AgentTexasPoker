#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAX_HANDS="${MAX_HANDS:-20}"
CONFIG_PATH="${CONFIG_PATH:-}"
RESUME_RUN_DIR="${RESUME_RUN_DIR:-}"
RUN_NAME="${RUN_NAME:-}"
LOG_ROOT="${LOG_ROOT:-}"

if [[ -z "$CONFIG_PATH" ]]; then
  echo "CONFIG_PATH is required. Use a wrapper under scripts/<model>/ or export CONFIG_PATH manually." >&2
  exit 1
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Missing config: $CONFIG_PATH" >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "Project: $ROOT_DIR"
echo "Config:  $CONFIG_PATH"
echo "Hands:   $MAX_HANDS"
if [[ -n "$RESUME_RUN_DIR" ]]; then
  echo "Resume:  $RESUME_RUN_DIR"
fi
if [[ -n "$RUN_NAME" ]]; then
  echo "RunName: $RUN_NAME"
fi
if [[ -n "$LOG_ROOT" ]]; then
  echo "Logs:    $LOG_ROOT"
fi

cmd=(python run_simulation.py --config "$CONFIG_PATH" --hands "$MAX_HANDS" --verbose)
if [[ -n "$RESUME_RUN_DIR" ]]; then
  cmd+=(--resume-run-dir "$RESUME_RUN_DIR")
fi
if [[ -n "$RUN_NAME" ]]; then
  cmd+=(--run-name "$RUN_NAME")
fi
if [[ -n "$LOG_ROOT" ]]; then
  cmd+=(--log-root "$LOG_ROOT")
fi

"${cmd[@]}"
