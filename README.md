# A-Stock Screener + Trading Log

A daily A-stock screener and trading journal system. Scans 5300+ A-shares each trading day at 15:35 CST, generates sector-flow and candidate reports, produces per-stock research briefs, logs buy/sell decisions, and computes discipline statistics.

## CLI Entry Points

All CLI scripts live under `a_stock/` and run via `python -m`:

### 1. Screener

```bash
# Full scan (short + mid strategies)
python -m a_stock.screener --date 2026-06-25 --strategy both

# Re-render HTML from cached SQLite data (no network)
python -m a_stock.screener --date 2026-06-25 --render-only

# Scan with a single strategy
python -m a_stock.screener --date 2026-06-25 --strategy mid
```

Output: `data/screen/daily/YYYY-MM-DD/report.html` + `candidates_*.json` + `sectors.json`

### 2. Research Brief

```bash
# Single stock brief
python -m a_stock.brief 000858

# Batch from latest screener candidates
python -m a_stock.brief --from-screener 2026-06-25 --top-n 10

# Custom date
python -m a_stock.brief 000858 --date 2026-06-20
```

Output: `data/screen/briefs/<code>/YYYY-MM-DD.json` and `YYYY-MM-DD.md`

### 3. Decision Log

```bash
# Record a buy
python -m a_stock.log buy 000001 --strategy short --price 10 --qty 100 --reason "breakout"

# Interactive buy (detects brief, pre-fills price)
python -m a_stock.log buy 000858 --strategy short

# Add to existing position
python -m a_stock.log add 000858 --strategy short --price 10.5 --qty 50

# Close a position
python -m a_stock.log close 1 --close-date 2026-07-01 --close-price 11 --close-reason target

# Update plan parameters
python -m a_stock.log plan 1 --plan-target 12 --plan-stop 9

# List open positions
python -m a_stock.log list --open

# Show position details
python -m a_stock.log show 1
```

Database: `data/decisions.sqlite`

### 4. Statistics

```bash
# Discipline report (last 90 days)
python -m a_stock.stats --discipline --window 90

# Overall stats
python -m a_stock.stats

# By strategy
python -m a_stock.stats --strategy short

# By stock code
python -m a_stock.stats --code 000858
```

### Utility Scripts

```bash
# Monte Carlo: P(达目标)
python -m a_stock.goal_sim

# 组合风险
python -m a_stock.risk_metrics

# 情绪温度
python -m a_stock.sentiment

# 深度研究 (DCF+Comps)
python -m a_stock.deep_research 600276 --json

# 宏观日历
python -m a_stock.macro_calendar list

# 决策记录
python -m a_stock.log list

# 待办系统
python -m a_stock.todo list

# 交易统计
python -m a_stock.stats

# 监控 dry-run
python -m a_stock.monitor --dry-run

# 调度器
python -m a_stock.scheduler session
```

## Architecture

```
┌─────────────────────────────────────────┐
│           Data Layer (a_stock/a_stock_data)  │
│  East Money API  ·  Tencent API        │
│  THS hot reasons · Yahoo Finance       │
│  Concept blocks  · Dragon & Tiger      │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│        Business Layer (a_stock/a_screen)     │
│  sector_scan  ·  candidate_filter       │
│  scoring  ·  brief_builder              │
│  snapshot  ·  decision_log              │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│          CLI Layer (a_stock/*.py)            │
│  screener  ·  brief  ·  log  ·  stats  │
│  cron scripts (scripts/cron/)           │
└─────────────────────────────────────────┘
```

## Project Structure

```
.
├── a_stock/
│   ├── a_stock_data/     # API wrappers (East Money, Tencent, THS, yfinance)
│   ├── a_screen/         # Scoring, filtering, brief building, decision log
│   ├── screener.py       # Main screener CLI
│   ├── brief.py          # Research brief CLI
│   ├── log.py            # Trading journal CLI
│   ├── stats.py          # Statistics & discipline CLI
│   ├── config.py         # Paths, scoring weights, rate limits
│   └── db.py             # SQLite helpers
├── tests/
│   ├── integration/      # Integration tests (skipped by default)
│   └── smoke/            # Smoke tests
├── scripts/
│   └── cron/             # Cron job definitions
├── data/
│   ├── screen/daily/     # Screener output (gitignored)
│   ├── screen/briefs/    # Research briefs (gitignored)
│   ├── decisions.sqlite  # Trading decision DB (gitignored)
│   └── screener.sqlite   # Screener history DB (gitignored)
├── analysis/             # Industry chain visualizations (static HTML)
├── docs/                 # Superpowers plan & spec docs
└── tmp/                  # Scratch scripts
```

## Tests

```bash
# Unit tests only (fast, no network)
PYTHONPATH=/Users/maerun/Library/Python/3.14/lib/python/site-packages:. .venv/bin/python -m pytest tests/ -v

# Include integration tests (requires network, skipped by default)
PYTHONPATH=/Users/maerun/Library/Python/3.14/lib/python/site-packages:. .venv/bin/python -m pytest tests/ --run-integration -v
```

## Cron

A `scripts/cron/a-stock-screen` file defines the daily schedule (Asia/Shanghai):

| Time   | Task                              |
|--------|-----------------------------------|
| 15:35  | `a_stock.screener` (scan + cache)      |
| 15:40  | `a_stock.screener --render-only`       |
| 15:45  | `a_stock.brief --from-screener`        |
| Sun 23:00 | `scripts/backup.sh`            |

## Saver Tip

Create a shell alias for daily use:

```bash
alias spl='git -C /Users/maerun/Documents/Projects/make-money pull && cd /Users/maerun/Documents/Projects/make-money && python -m a_stock.log list --open'
```

> **Disclaimer:** This project is for personal research and educational purposes only. It does not constitute investment advice. See `CLAUDE.md` for the analysis HTML files documentation.