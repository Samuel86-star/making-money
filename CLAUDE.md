# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Two self-contained HTML files live in `analysis/technology/`:
- `AI-Compute-Industry-Chain.html` — interactive Chinese-language visualization of the AI 算力 (compute) industry chain.
- `HBM-supply-chain.html` — HBM 国产化设备链 deep-research dossier.

No build step, no dependencies, no framework, no package manager. Open either file directly
in a browser; edit in any text editor. There are no test, lint, or build commands to run.

## Architecture

Everything lives in one file: markup, CSS (in `<style>`), and JS (in `<script>`) at the
end of `<body>`. Vanilla JS, no framework. Four visual sections share one data source:

1. **Concentric "factory" rings** (`.ring.r0`–`.r5`) — six nested circles, GPU brain at
   center (r0) outward to networking (r5). Clicking/hovering a ring updates the `.info`
   side panel via `show(k)`.
2. **Info panel** (`.info`) — detail view for the selected ring.
3. **Matrix cards** (`.mcards`) — generated in JS from the same `data` object; clicking
   a card calls `show(k)` and scrolls back to the rings.
4. **Static sections** — flow chain, three-keyword cards (PCB/CPO/MLCC), and insight
   block; these are hand-written HTML, not data-driven.

### The single source of truth

`data` (an object keyed `r0`–`r5`) drives both the ring info panel and the matrix cards.
Each entry has: `tag`, `c` (CSS color var), `title`, `role`, `desc`, `players`,
`dom` (国产水平 1–5), `domLabel` (e.g. `"国产 ★★（有但受制裁）"`), and `profit`.
`oneLiner` is a parallel object adding the matrix card subtitle.

When adding/editing a link in the chain, change it **once** in `data` — both the ring
panel and the matrix card render from it.

### Conventions worth preserving

- **Domestic-level color scale** (`domColor` map): `1=#dc2626` red (weakest) →
  `5=#0891b2` teal (strongest). Meter bar widths are `dom*20%`. The matrix card
  border-left class `lv1`–`lv5` mirrors this. Keep all three in sync when adding a level.
- **Ring hit-targets**: the `.ring` circles have `pointer-events:none`; the inner label
  `<div>` re-enables events (see the comment near line 258). This prevents an outer ring
  from swallowing clicks meant for an inner ring. Don't move events back onto `.ring`.
- **Star ratings** (`★★`) are embedded in `domLabel` and parsed out via regex
  (`d.domLabel.match(/★+/)`) for display — keep the `★` characters if you edit a label.
- CSS custom properties (`--c0`…`--c5`, `--bg`, `--ink`, etc.) are defined on `:root`
  and referenced in both CSS and the `data[k].c` values.

## Content note

The page is dated 2026/06/24 and carries a "不构成投资建议" (not investment advice)
disclaimer in the footer. Company names, market-share claims, and dates are editorial
content — verify against current sources before treating as fact.

---

## A股决策支持系统 (新主项目, 2026-06-27 起)

> **角色: 我是这个用户的理财顾问。** 不替下单, 推送后用户决策。
> 完整状态/目标/持仓/工具见 `data/PROJECT_STATE.md`. 任何会话开头先读这个。

### 目标
2026-12-31 前 78,788 → 100,000 (+26.9% in 185 天)。
P(达成) 蒙特卡洛基线 0.1% → 必须主动加仓+择时。

### 工具 (`a_stock/`)
9 个核心脚本, 见 `a_stock/MONITOR_README.md`:
- `goal_sim` 蒙特卡洛, `risk_metrics` 风险, `position_sizer` 凯利
- `macro_calendar` 日历, `sentiment` 情绪, `notifier` 推送
- `monitor` 主循环, `rules.yaml` 规则, `setup_cron.sh` 安装

### 工作模式
脚本(cron)盯盘 → 命中规则 → Mac 弹窗 → 用户在券商app下单。
我不直接下单, 也不"AI 替判断" — 决策权在用户。

### 沟通
- Caveman 模式 (用户指定)
- 数字优先, 不确定就说不确定
- 任何建议必带仓位%/止损价/目标价

### DB
- 主库: `data/decisions.sqlite`
- 写入: `python -m a_stock.log {buy|add|close|reduce|plan|watchlist}`
- 不要删持仓! 600276/159915 等是真实数据, 测试用 T_ 前缀
