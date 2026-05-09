#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="/tmp/daily_scanner_latest.log"
REPORT_FILE="$SCRIPT_DIR/latest_daily_report.md"

cd "$SCRIPT_DIR"

if ! timeout 900 /root/.hermes/hermes-agent/venv/bin/python -u "$SCRIPT_DIR/daily_scanner.py" >"$LOG_FILE" 2>&1; then
  cat "$LOG_FILE"
  exit 1
fi

if [ ! -s "$REPORT_FILE" ]; then
  echo "扫描执行完成，但未生成最终报告文件: $REPORT_FILE"
  echo "--- scanner log ---"
  cat "$LOG_FILE"
  exit 1
fi

cat "$REPORT_FILE"
