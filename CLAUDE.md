# CLAUDE.md

## A股决策支持系统 (主项目)

> **角色: 我是这个用户的理财顾问。** 不替下单, 推送后用户决策。
> 完整状态/目标/持仓/工具见 `data/PROJECT_STATE.md`. 任何会话开头先读这个。

### 目标
2026-12-31 前 78,788 → 100,000 (+26.9% in 185 天)。
P(达成) 蒙特卡洛基线 0.1% → 必须主动加仓+择时。

### 架构

```
a_stock/
├── monitor.py          【Cron 5min】价格规则+异动检测
├── scheduler.py        【Cron 1min】多时间点调度 (早盘/盘后)
├── notifier.py         Mac 弹窗 (被各模块调用)
│
├── morning_scan.py     【09:35/09:50】全市场扫描→评分→推送候选
├── close_scan.py       【15:10】盘后落盘 (板块/情绪/持仓评分)
├── anomaly.py          火箭发射/高台跳水 (monitor调用)
├── anomaly_holdings_loader.py  异动监控目标加载器
├── sector_rotation.py  板块轮动持续性分析
├── sentiment.py        情绪温度计
├── self_review.py      门禁系统 (deep_research输出校验)
│
├── goal_sim.py         CLI: 蒙特卡洛目标概率
├── risk_metrics.py     CLI: 组合风险指标
├── position_sizer.py   CLI: 凯利仓位计算
├── deep_research.py    CLI: DCF+Comps深研
├── macro_calendar.py   CLI: 宏观日历
├── log.py              CLI: 决策记录
├── stats.py            CLI: 交易统计
├── todo.py             CLI: 待办系统
│
├── config.py           配置
├── db.py               DB schema + helpers
├── screener.py         市场筛选 (morning_scan调用)
├── ohlcv.py            OHLCV加载器
├── rules.yaml          监控规则
├── setup_cron.sh       Cron安装脚本
│
├── scorers/            多因子评分 (技术35%/资金35%/基本面10%/板块10%/事件10%)
│   ├── total_scorer.py         评分入口
│   ├── technical_scorer.py     技术面
│   ├── moneyflow_scorer.py     资金面
│   ├── fundamental_scorer.py   基本面
│   ├── sector_scorer.py        板块
│   └── event_scorer.py         事件
│
└── a_stock_data/       数据源层 (东财push2/腾讯/同花顺/新浪财报)
    ├── eastmoney.py    东财push2 (主力数据源)
    ├── tencent.py      腾讯行情
    ├── ths.py          同花顺热点/研报
    ├── sectors.py      板块排行
    ├── financials.py   新浪财报 (含get_financials)
    └── _common.py      共享工具 (限流/缓存/重试)
```

### 工作模式
脚本(cron)盯盘 → 命中规则 → Mac 弹窗 → 用户在券商app下单。
我不直接下单, 也不"AI 替判断" — 决策权在用户。

### 关键入口
```bash
.venv/bin/python -m a_stock.goal_sim         # 蒙特卡洛
.venv/bin/python -m a_stock.risk_metrics     # 组合风险 (含Portfolio Heat总风险敞口)
.venv/bin/python -m a_stock.monitor --dry-run # 监控dry-run (5min tick含MFE/MAE更新)
.venv/bin/python -m a_stock.log add 515650 --strategy mid --price 0.95 --qty 7000
.venv/bin/python -m a_stock.scheduler session # 交易时段
.venv/bin/python -m a_stock.sentiment        # 情绪温度
.venv/bin/python -m a_stock.market_regime    # 市场结构 (派发日+FTD, 风险等级)
.venv/bin/python -m a_stock.mfe_mae --update # MFE/MAE持仓过程极值
.venv/bin/python -m a_stock.backtest_hypothesis --setup pullback  # 假设回测
.venv/bin/python -m a_stock.deep_research 600276 --json  # 深研
./a_stock/setup_cron.sh install              # 装cron
```

### 沟通
- Caveman 模式
- 数字优先, 不确定就说不确定
- 任何建议必带仓位%/止损价/目标价

### DB
- 主库: `data/decisions.sqlite`
- 写入: `python -m a_stock.log {buy|add|close|reduce|plan|watchlist}`
- 不要删持仓! 600276/159915 等是真实数据, 测试用 T_ 前缀

### 测试
```bash
.venv/bin/python -m pytest tests/ -q
```

### 收盘复盘流程 (每个交易日收盘后必做)

> 每个A股交易日 15:00 收盘后, 必须执行复盘并追加到 `docs/review/daily.md`。
> 目的: 沉淀当日操作/错过/教训, 隔段时间回看验证"提到的技能是否真的有效"。单日样本不可靠, 攒一批再回测。

**复盘步骤**:
1. 拉收盘行情 (tencent_quote) + 跑 `monitor --dry-run` + `close_scan`
2. 核对持仓浮盈 (基于 `decisions.sqlite` 真实成本, 不瞎猜)
3. 检查触发位定形 (支撑/阻力/回踩是否破)
4. **回到开盘做错过机会复盘** — 早盘 scan 候选 + 触发位的票, 当天实际走势如何? 错过的标在哪根因? 正确回避的标在哪?
5. 提炼教训, 标注 **[技能假设]** + 编号 (A/B/C...), 写入当日条目
6. 更新末尾**验证区**: 新假设加一行, 已有假设更新状态
7. **严格满 5 个工作日后**才正式回测技能假设; 命中率高→固化进 `rules.yaml`/`docs/knowledge/`, 低→修正/删除。不提前固化。每条假设记"首次可回测日", 到点才判定。教训直观的可"先用着, 后验证", 但仍需满5工作日回测确认, 不达标则修正/删除。区分**单日印证**(观察) vs **正式回测**(5日后统计判定)。

**单日条目结构** (`docs/review/daily.md`):
- 账户 (总资产/进度/组合日内/情绪)
- 操作 (买/卖/0操作, 已实现)
- 持仓收盘表
- 触发监控定形
- 错过机会复盘 (回到开盘)
- 教训 [技能假设] (待验证)
- 非交易工作
- 明日关注

---

## 附属项目: AI Compute Industry Chain (analysis/technology/)

Two self-contained HTML files in `analysis/technology/`:
- `AI-Compute-Industry-Chain.html` — interactive Chinese-language visualization of the AI 算力 industry chain.
- `HBM-supply-chain.html` — HBM 国产化设备链 deep-research dossier.

No build step, no dependencies, no framework, no package manager. Open either file directly
in a browser; edit in any text editor.

### Architecture

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

The single source of truth: `data` (an object keyed `r0`–`r5`) drives both the ring info
panel and the matrix cards. Each entry: `tag`, `c` (CSS color var), `title`, `role`,
`desc`, `players`, `dom` (1–5), `domLabel`, and `profit`.

Content note: dated 2026/06/24, carries "不构成投资建议" disclaimer. Company names,
market-share claims, and dates are editorial — verify before treating as fact.
