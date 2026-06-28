# Session: 架构重绘 + monitor加固 + strategies设计

> 2026-06-27 17:30-19:30 · 约2h
> 末次更新: 2026-06-27 (规划完成, 待执行)

## 做了什么

### 1. 架构图彻底重绘 (docs/architecture/) ✅

**问题**: 旧图还是 v0.5→v1.0 过渡态, 实际代码已接近 v1.0.

**改动**: 删除 `2026-06-27-system-architecture.md` + `_preview.html`, 新建:
- `system-architecture.md` — Mermaid 源码, 9 张图
- `preview.html` — 深色金融风格预览, 浏览器直接打开

**新图反映真实架构**: 8 层 (数据源/发现/评分/确认/调度/执行/复盘/辅助) + 存储. 后续 strategies/ 设计也回填进图 (Signal Bridge 子图).

### 2. monitor 加固 (a_stock/monitor.py) ✅

**WAL 模式**: 3 处加 `PRAGMA journal_mode=WAL` — `_ensure_monitor_log_table`, `_load_holdings`, INSERT 连接. 解决 `goal_sim`/`risk_metrics` 并发读与 monitor 写互相阻塞.

**结构化错误日志**:
- 新增 `MONITOR_ERROR_LOG = data/monitor_errors.jsonl`
- 新增 `_log_error(module, func, exc)` — 写 JSONL + push 桌面通知
- `_run_impl` 和 `_check_anomalies` 各加 try/except 兜底
- 内层 try/except 防护日志写入自身失败

回归测试: 38 passed, 16 skipped, dry-run 正常.

### 3. strategies/ 调研 + 设计 + 规划 ✅ (代码未实现)

**pyc 反编译**: 确认已删源代码结构 — base/registry/runner + 3 策略 (near_limit_up, trend_breakout, oversold_bounce)

**GitHub 调研**: 翻 8 个项目 — tickflow(骨架), KHunter(registry), CopilotQuant(Signal quality), Qlib(太重跳过), QuantsPlaybook(因子源), Alpacalyzer(protocol)

**设计方案: Signal Bridge**
```
strategies/ → SignalVote → topM → morning_scan → scorers 5维评分 → watchlist
```
- 5 策略: trend_breakout / oversold_bounce / near_limit_up / moneyflow_surge / sector_momentum
- Signal 数据结构: {code, action, confidence, strategy, reason}
- runner 并行跑所有策略, SignalVote 聚合按 confidence 排序
- 不与 scorers/ 重叠: 策略=快速发现, 评分=深度确认
- 架构图已更新反映此设计

**设计文档**: `docs/superpowers/specs/2026-06-27-strategies-design.md` (commit 01bccfb)

**实现计划**: `docs/superpowers/plans/2026-06-27-strategies-implementation.md` (commit 71bbf96)
- 14 个 Task, TDD 流程 (失败测试 → 实现 → 通过 → 提交)
- 一个设计偏离: `sector_momentum` 因 `sectors.py` 无板块成分股接口, 改用 sector_rotation verdict 市场门 + 候选 change_pct

**关键接口事实 (已核实代码):**
- `load_ohlcv(code)` 列名**小写** `open/high/low/close/volume`, 含 `date` 列
- `fetch_market_stocks(top_n)` 返回 `[{"code","name","change_pct","net_flow"}]`, 已按净流入降序
- `sector_rotation.analyze()` 返回 `RotationResult(strongest_repeat_name, current_leader, current_streak_days, verdict, ...)`
- `sectors.py` **无板块→成分股接口** (sector_momentum 设计偏离根因)
- ohlcv 数据已就绪: 全市场 5206 只 parquet, 大部分 244 根K线, 远超 ma60 需求

### 4. 已修复缺口

| Gap | 状态 |
|-----|------|
| strategies/ 空目录 | 设计+规划完成, 代码待执行 |
| monitor 无 WAL | ✅ 已修补 |
| 异常无结构化日志 | ✅ 已修补 |
| parquet | 跳过 (不需要) |
| 多券商对接 | 设计如此, 非缺口 |

## 关键命令

```bash
# 验证
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m a_stock.monitor --dry-run

# 架构预览
open docs/architecture/preview.html
```

## 已完成 — strategies/ 实现

全部 14 Task 通过 subagent-driven dev 落地 (Batch A 骨架 + Batch B 5策略 + Batch C 集成), 每批 review 后提交.

**批次划分:**
- **Batch A (Task 1-6) 骨架**: Signal/SignalVote/aggregate, BaseStrategy 三段式+limit_pct, runner.build_indicators 共享指标, registry 目录反射自动注册, run_all/run_top, __init__ 导出
- **Batch B (Task 7-11) 5策略**: trend_breakout(0.7) / oversold_bounce(0.5) / near_limit_up(0.6) / moneyflow_surge(0.6) / sector_momentum(0.5)
- **Batch C (Task 12-14) 集成**: 冒烟测试 (tests/smoke/test_strategies_smoke.py) + morning_scan 接入 runner (策略候选 ∪ screener top10) + 最终回归

**review 中抓到的关键 bug:**
- verdict emoji 死代码 (sector_momentum 用了未定义表情符)
- 封板 rounding (near_limit_up 距涨停百分比未取整)
- change_pct 语义 (runner 用 close/prev_close 而非 (close-open)/open)
- Wilder RSI (原实现用 SMA 平滑, 改为 Wilder EMA, alpha=1/period)

**回归验证 (2026-06-28):** 77 passed, 16 skipped, 0 failures. morning_scan dry-run 策略层产出 6 只候选, monitor dry-run 正常.

## Git 状态

- 设计 spec: commit 01bccfb
- 实现计划: commit 71bbf96
- Batch A 骨架: 3a02fce..5e3cada + review 修复 ad7029e / 1b74d4f
- Batch B 5策略: 9a4fdb2..ba59dc5 + review 修复 c128a82
- Batch C 集成: 191dc1e (morning_scan 接入 runner + 冒烟测试)
- 14 Task 全部完成, 无待执行项
