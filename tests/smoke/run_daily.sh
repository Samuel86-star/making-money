#!/bin/bash
# tests/smoke/run_daily.sh
# Phase 3 smoke test — runs the full screener E2E on a recent A-share trading day.
set -e
cd "$(dirname "$0")/../.."

# Use the most recent A-share trading day; override with TRADE_DATE env var for manual runs.
TRADE_DATE=${TRADE_DATE:-$(python -c "from datetime import date, timedelta; print((date.today() - timedelta(days=1)).isoformat())")}

echo "=== Phase 3 smoke: $TRADE_DATE ==="
python py/screener.py --date "$TRADE_DATE" --strategy short --top-n 5 --enrich-top 3
python py/screener.py --date "$TRADE_DATE" --render-only

# Verify artifacts
test -f "data/screen/daily/$TRADE_DATE/candidates_short.json" || { echo "FAIL: no candidates_short.json"; exit 1; }
test -f "data/screen/daily/$TRADE_DATE/report.html" || { echo "FAIL: no report.html"; exit 1; }
echo "PASS"