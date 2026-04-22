#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/newsletter-$(date -u +%Y-%m-%d).log"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"
exec >> "$LOG_FILE" 2>&1

on_error() {
  local exit_code=$?
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] FAILED Nigerian Politics Newsletter production run exit_code=$exit_code"
  exit "$exit_code"
}

trap on_error ERR

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting Nigerian Politics Newsletter production run"
venv/bin/python main.py --send-production --confirm-production
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] SUCCESS Nigerian Politics Newsletter production run"
