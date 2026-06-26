# A股辅助决策系统 设计文档

| 字段 | 值 |
|---|---|
| 日期 | 2026-06-26 |
| 状态 | Design — 待用户审阅 |
| 范围 | 三件套(Screener v2 / Research Brief / 复盘日志) |
| 策略 | 短线 + 中线 双轨 |
| 时间预算 | <30 分钟/天,高自动化 |

---

## 1. 概述

构建一个辅助 A股投资决策的系统,目标:**不盲目追赛道或个股,基于数据 + 研报 + AI 跨信号分析做有依据的判断**。

核心工作流:
1. cron 每日 15:35 自动跑全市场扫描
2. 15:45 自动生成 top 候选 brief 快照
3. 用户 <30 min 看日报 + 选股
4. 对候选股触发 brief → 读快照 → 让 AI 做综合分析 → 决策
5. 决策写复盘日志,带计划 vs 实际
6. 季度跑统计,看胜率与纪律性,改进下季策略

**关键架构选择**:AI 分析不由 cron 调 LLM API,而由 Claude Code 在对话中读取 brief 快照 JSON 完成,结果写回 `ai_analysis` 字段。这样不锁 LLM 供应商、不花 API 钱、可追溯"当时 AI 怎么说的"。

---

## 2. 目标与约束

### 用户目标
- 不盲目追赛道/个股,做有依据的判断
- 通过看研报 + AI 综合分析补自身金融知识短板
- 复盘量化(胜率、纪律性),季度改进

### 工程约束
- **海外网络**:mootdx TCP 7709 不通;东财偶发风控
- **预算紧**:无 LLM API 预算,无云服务预算
- **时间紧**:每天 <30 min 在系统上
- **现有资产保留**:5197 只 OHLCV parquet / 5529 列表 / 5 个 py 脚本不丢
- **低依赖**:不引入 akshare(已知不稳定的中间层)

### 成功标准
- 每天 16:00 前自动产出日报,无需手动触发
- top 10 短线 + top 10 中线 brief 自动落盘
- 决策记录 schema 严格,纪律性可统计
- 单股 brief < 30 秒,全市场扫 < 15 分钟

---

## 3. 范围与非目标

### 范围(本期做)
- Screener v2:短线 + 中线双轨评分,top 100 enrichment
- Research Brief:单股快照(基本面/资金/板块/研报/一致预期/AI 分析)
- 复盘日志:重量级 schema + 纪律性统计
- a-stock-data 集成:11 个核心端点 + 4 个保留端点
- cron 自动化 + 冒烟测试
- 单元 + 集成 + 冒烟三层测试

### 非目标(本期不做)
- Web UI / 移动端
- 自动交易 / 券商对接
- LLM API 自动分析(由 Claude Code 在对话中做)
- 实时盘中推送
- 多账户 / 家庭组合
- 税务计算
- 美股 / 港股 / 基金
- 复杂技术指标(MACD/RSI/布林带)

### 后续扩展(留接口,本期不实现)
- `a_screen/backtest.py`:用 screener 跑历史回测
- `a_screen/alert.py`:盘中监控 + 推送
- iwencai 接入(若列表+标题不够)
- 周报/月报聚合 HTML
- 行业热力图

---

## 4. 架构

### 三层架构

```
┌─────────────────────────────────────────────────────┐
│ Layer 3: 入口脚本                                  │
│   py/screener.py  py/brief.py  py/log.py  py/stats.py│
├─────────────────────────────────────────────────────┤
│ Layer 2: 业务编排(py/a_screen/)                    │
│   sector_scan, candidate_filter, brief_builder,     │
│   snapshot, decision_log                            │
├─────────────────────────────────────────────────────┤
│ Layer 1: 数据访问                                  │
│   py/a_stock_data/  (vendored from SKILL.md)         │
│   py/ohlcv.py        (parquet 读)                   │
│   py/db.py           (SQLite 封装)                  │
└─────────────────────────────────────────────────────┘
```

**关键边界**:
- Layer 1 只做 HTTP/文件 IO,无业务逻辑
- Layer 2 纯 Python 计算,无 HTTP(只接 Layer 1 返回的 dict)
- Layer 3 是 CLI 入口,组合 Layer 2 步骤

**测试可行性**:
- Layer 2 单元测试用 mock Layer 1,不依赖网络
- Layer 1 集成测试真发请求,标记 skip by default
- Layer 3 冒烟测试跑 E2E

---

## 5. 目录结构

### py/

```
py/
├── a_stock_data/        # 从 a-stock-data SKILL.md vendor 的 helpers
│   ├── __init__.py
│   ├── _common.py        # em_get, EM_MIN_INTERVAL, EM_SESSION, UA, get_prefix, normalize_code
│   ├── tencent.py        # tencent_quote(PE/PB/市值/换手/涨跌停)
│   ├── eastmoney.py      # reports, industry_reports, concept_blocks, fund_flow_minute,
│   │                     #   stock_fund_flow_120d, daily_dragon_tiger
│   ├── ths.py            # ths_hot_reason, ths_eps_forecast, hsgt_realtime
│   ├── sectors.py        # industry_comparison
│   ├── news.py           # eastmoney_stock_news, eastmoney_global_news(保留,舆情)
│   ├── pdf.py            # download_pdf(保留,偶尔下研报)
│   ├── financials.py     # sina_financial_report(保留,基本面)
│   └── filings.py        # cninfo_announcements(保留,公告事件)
│
├── a_screen/            # 业务编排(Layer 2)
│   ├── __init__.py
│   ├── sector_scan.py
│   ├── candidate_filter.py
│   ├── brief_builder.py
│   ├── snapshot.py
│   └── decision_log.py
│
├── screener.py          # 入口 1:每日扫描
├── brief.py             # 入口 2:生成个股 brief
├── log.py               # 入口 3:复盘记录
├── stats.py             # 入口 4:复盘统计
│
├── ohlcv.py             # 读 parquet
├── db.py                # SQLite 封装
├── config.py            # 路径、限流、时区、scoring weights
│
├── fetch-ashare-list.py # (保留,不动)
├── fetch-trending.py    # (保留,不动)
├── download-ohlcv.py    # (保留,不动)
├── backtest-volume.py   # (保留,不动)
└── closeout-screener.py # (废弃,顶部 DEPRECATED 注释,功能并入 screener.py)
```

### data/

```
data/
├── ohlcv/*.parquet            # 5197 只 K线(现有,~50MB)
├── a_share_list.json          # 5529 列表(现有)
├── trending/                  # (保留)
├── screen/                    # 新建
│   ├── daily/YYYY-MM-DD/
│   │   ├── sectors.json
│   │   ├── candidates_short.json
│   │   ├── candidates_mid.json
│   │   └── report.html
│   └── briefs/<code>/
│       └── YYYY-MM-DD.json    # brief 快照
│       └── YYYY-MM-DD.md      # brief markdown
├── closeout/*.json            # 旧输出(冻结,gitignore)
├── decisions.sqlite           # 复盘主库
├── screener.sqlite            # 扫描事实库
├── backup/                    # 每周 .backup 落盘
└── .cache/em/                 # em_get URL 缓存(gitignore)
```

---

## 6. SQLite Schema

### `data/decisions.sqlite`

```sql
-- 一次操作 = 一个 lot。同一只股可多次操作(分批/DCA)。
CREATE TABLE decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL,
    name            TEXT,
    strategy        TEXT NOT NULL CHECK(strategy IN ('short', 'mid')),
    action          TEXT NOT NULL CHECK(action IN ('buy', 'add', 'sell', 'close')),
    decision_date   TEXT NOT NULL,         -- YYYY-MM-DD
    decision_time   TEXT,                  -- HH:MM:SS
    price           REAL NOT NULL,
    quantity        INTEGER NOT NULL,
    amount          REAL,
    reason          TEXT,
    brief_snapshot_path TEXT,

    -- 计划
    plan_stop_loss      REAL,
    plan_target         REAL,
    plan_hold_days      INTEGER,
    plan_max_position_pct REAL,

    -- 实际结果
    close_date      TEXT,
    close_price     REAL,
    close_reason    TEXT CHECK(close_reason IN ('stop_loss', 'target', 'manual', 'expired')),
    pnl_pct         REAL,                  -- (close_price - price) / price * 100

    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),

    INDEX idx_code (code),
    INDEX idx_strategy_date (strategy, decision_date),
    INDEX idx_open (close_date)
);

-- 关注列表(可选,主靠主动发现但保留手动加入入口)
CREATE TABLE watchlist (
    code        TEXT PRIMARY KEY,
    name        TEXT,
    theme       TEXT,
    note        TEXT,
    added_at    TEXT DEFAULT (datetime('now'))
);
```

### `data/screener.sqlite`

```sql
-- 每日扫描候选
CREATE TABLE candidate_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date           TEXT NOT NULL,
    strategy            TEXT NOT NULL CHECK(strategy IN ('short', 'mid')),
    code                TEXT NOT NULL,
    name                TEXT,
    sector              TEXT,
    concept_primary     TEXT,
    net_flow            REAL,
    change_pct          REAL,
    pe_ttm              REAL,
    pb                  REAL,
    mcap_yi             REAL,
    turnover_pct        REAL,
    report_count_7d     INTEGER,
    hot_reason          TEXT,
    on_dragon_tiger     INTEGER DEFAULT 0,
    score               REAL,
    raw_data_path       TEXT,

    UNIQUE(scan_date, strategy, code),
    INDEX idx_strategy_date (strategy, scan_date),
    INDEX idx_code (code)
);

-- 板块扫描日维度
CREATE TABLE sector_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date       TEXT NOT NULL,
    sector_type     TEXT NOT NULL CHECK(sector_type IN ('industry', 'concept')),
    name            TEXT NOT NULL,
    change_pct      REAL,
    net_flow        REAL,
    leader_name     TEXT,
    leader_code     TEXT,
    rank            INTEGER,

    UNIQUE(scan_date, sector_type, name),
    INDEX idx_date (scan_date)
);

-- 每日日报元数据
CREATE TABLE daily_summary (
    date                TEXT PRIMARY KEY,
    generated_at        TEXT NOT NULL,
    short_count         INTEGER,
    mid_count           INTEGER,
    sector_count        INTEGER,
    report_path         TEXT,
    brief_snapshots     INTEGER,
    status              TEXT DEFAULT 'ok'
);
```

**数据决策**:
- `decisions.action` 用 'buy/add/sell/close':支持分批建仓
- `name` 冗余存:避免显示时 join
- 时间全用 TEXT ISO8601:跨时区易读,字符串排序等价时间排序
- `brief_snapshot_path` 是 string 引用:快照本体在文件系统
- 无 `positions` 实体表:当前持仓 = `decisions WHERE close_date IS NULL` 的视图
- `candidate_history` 用 `UNIQUE(scan_date, strategy, code)`:UPSERT 友好

---

## 7. a-stock-data 集成范围

### Vendor 端点(15 个,分两档)

**Tier 1 必用(11 个)**
| 来源 | 函数 | 文件 |
|---|---|---|
| 共用 | em_get / EM_MIN_INTERVAL / EM_SESSION / UA / get_prefix / normalize_code | `_common.py` |
| 行情 | tencent_quote | `tencent.py` |
| 研报 | eastmoney_reports, eastmoney_industry_reports | `eastmoney.py` |
| 研报 | ths_eps_forecast | `ths.py` |
| 信号 | ths_hot_reason, eastmoney_concept_blocks | `ths.py`, `eastmoney.py` |
| 信号 | eastmoney_fund_flow_minute, industry_comparison | `eastmoney.py`, `sectors.py` |
| 资金 | stock_fund_flow_120d, daily_dragon_tiger | `eastmoney.py` |
| 资金 | hsgt_realtime | `ths.py` |

**Tier 2 保留(4 个,舆情/分析时按需)**
| 来源 | 函数 | 文件 |
|---|---|---|
| 新闻 | eastmoney_stock_news, eastmoney_global_news | `news.py` |
| 研报 | download_pdf | `pdf.py` |
| 财报 | sina_financial_report | `financials.py` |
| 公告 | cninfo_announcements | `filings.py` |

### 不 vendor(10 个,顶部注释说明)

- mootdx 全部(海外 TCP 7709 不通)
- iwencai(不申请 API Key)
- baidu_kline_with_ma(yfinance 已有 K 线)
- lockup_expiry(非主要)
- margin_trading / block_trade / holder_num_change / dividend_history(非主要)
- dragon_tiger_board 单股版(用 daily_dragon_tiger 全市场版替代)

### 改造点(只 3 处)

1. `EM_MIN_INTERVAL` 默认 1.5s(批量场景友好,可通过 config 调到 1.0)
2. `em_get` 加本地 URL 缓存(`data/.cache/em/`,TTL 15 分钟)
3. `tencent_quote` 加 retry(3 次 + 1s 间隔)

---

## 8. 模块设计

### 8.1 Screener v2

**CLI**:
```bash
python py/screener.py                        # 当日
python py/screener.py --date 2026-06-26      # 指定日期
python py/screener.py --strategy short       # 单策略
python py/screener.py --strategy mid
python py/screener.py --top-n 30
python py/screener.py --enrich-top 50
python py/screener.py --no-html
python py/screener.py --render-only          # 只重渲染 HTML
python py/screener.py --force                # 强制重抓
```

**数据流**:
```
Step 1: 市场级数据(~5s,免限流)
  industry_comparison(top_n=30)
  ths_hot_reason(date)
  daily_dragon_tiger(trade_date)

Step 2: push2 clist 5197 只(~3s)
  输出:全市场按主力净流入排序的 raw list

Step 3: 短线/中线初筛(纯计算)
  short: 净流入>0,涨幅 1-7%
  mid: 20日累计净流入>0,PE 0-50,市值>50 亿
  各取 top 100 进 enrichment 池

Step 4: enrichment top 100(em_get,~2-3min)
  每只 4 端点:
    eastmoney_concept_blocks
    stock_fund_flow_120d
    eastmoney_reports(max_pages=1)
    eastmoney_fund_flow_minute(短线才要)

Step 5: 评分(纯计算,config.SCORING)

Step 6: 落盘
  screener.sqlite:candidate_history(200 行)
  screener.sqlite:sector_history
  screener.sqlite:daily_summary
  data/screen/daily/<date>/*.json
  data/screen/daily/<date>/report.html
```

**Scoring weights**(`config.py`):
```python
SCORING = {
    "short": {
        "net_flow_rank":     30,
        "change_pct_band":   20,
        "sector_alignment":  20,
        "report_count_7d":   15,
        "hot_reason_hit":    15,
    },
    "mid": {
        "valuation":         25,
        "fund_flow_20d":     20,
        "report_coverage":   20,
        "theme_catalyst":    20,
        "tech_position":     15,
    },
}
```

### 8.2 Research Brief

**CLI**:
```bash
python py/brief.py 000858                      # 单股
python py/brief.py 000858 --strategy short     # 强调短线
python py/brief.py --from-screener 2026-06-26  # 批量
python py/brief.py --from-screener today
python py/brief.py 000858 --force              # 强制重抓
```

**输出物**(per code+date):
- `data/screen/briefs/<code>/YYYY-MM-DD.json` — 数据快照
- `data/screen/briefs/<code>/YYYY-MM-DD.md` — markdown 报告

**快照结构**:
```json
{
  "meta": {
    "code": "000858", "name": "五粮液",
    "generated_at": "2026-06-26T15:42:00+08:00",
    "trigger": "manual | from_screener"
  },
  "snapshot_date": "2026-06-26",
  "fundamentals": { "price": 168.50, "pe_ttm": 22.5, "pb": 4.8,
                    "mcap_yi": 6543, "industry": "白酒", ... },
  "membership":    { "industries": [...], "concepts": [...], "regions": [...] },
  "fund_flow":     { "today": {...}, "5d_cumulative": 56789012, "20d_cumulative": 234567890 },
  "research":      { "report_count_30d": 12, "reports": [...] },
  "consensus":     { "eps_forecasts": [...], "consensus_target_price": 195.0 },
  "hot_signal":    { "is_today_hot": false, "reason": null },
  "dragon_tiger":  { "30d_count": 0, "last_appearance": null },
  "northbound":    { "5d_net_inflow": -12345678, "hold_market_cap_yi": 234.5 },
  "screener_score":{ "short": 78.5, "mid": 62.3, "scan_date": "2026-06-26" },
  "risks":         [ "PE 22.5 高于白酒行业中位数 18.3", ... ],
  "ai_analysis":   null
}
```

**AI 移交流程**:
```
[脚本] brief.py 000858 → 抓数据 → 写 JSON + MD(ai_analysis=null)
[你]   打开 MD,看 1-7 节数据
[你]   "分析 000858"
[我]   Read JSON → 写 ai_analysis 字段 → 重生成 MD 第 8 节
[你]   决策 → log.py buy
```

**缓存**:
- 同 code+date 二次 brief 不重抓(直接读 JSON 重出 MD)
- `--force` 强制重抓
- `ai_analysis` 可多次覆盖,带 `ai_analyzed_at` 时间戳

### 8.3 复盘日志

**log.py CLI**:
```bash
# 简化模式(自动检测 brief)
python py/log.py buy 000858
# 交互式:qty / reason / plan stop / target / hold / max_pct

# 显式模式
python py/log.py buy 000858 \
  --price 168.50 --qty 100 \
  --reason "短线主力净流入,板块共振" \
  --from-brief data/screen/briefs/000858/2026-06-26.md \
  --plan-stop 160 --plan-target 185 --plan-hold 5 --plan-max-pct 10 \
  --strategy short

# 加仓
python py/log.py add 000858 --price 165 --qty 50 --reason "回调加仓"

# 平仓
python py/log.py close <id> --close-price 178 --close-reason target

# 改计划
python py/log.py plan <id> --plan-stop 162

# 查询
python py/log.py list --open
python py/log.py show <id>
```

**stats.py CLI**:
```bash
python py/stats.py                             # 总览
python py/stats.py --strategy short            # 按策略
python py/stats.py --code 000858               # 按股
python py/stats.py --discipline                # 纪律性专项
python py/stats.py --recent 20
python py/stats.py --export csv > out.csv
```

**纪律性指标**:
- 止盈执行率 = (close_reason='target' AND pnl>0) / (pnl>0 总数)
- 止损执行率 = (close_reason='stop_loss' AND pnl<0) / (pnl<0 总数)
- 提前止盈率 = (close_reason='manual' AND pnl>0) / 总数
- 恐慌止损率 = (close_reason='manual' AND pnl<0) / 总数
- 平均持有偏离 = AVG(实际天数 - 计划天数)

---

## 9. 数据流与 cron 调度

### Cron(A股交易日 15:35-15:50)

```cron
# Asia/Shanghai
35 15 * * 1-5  python3 py/screener.py --no-html > data/screen/cron.log 2>&1
40 15 * * 1-5  python3 py/screener.py --render-only
45 15 * * 1-5  python3 py/brief.py --from-screener today --top-n 10
```

### 端到端时序

```
15:00  A股收盘
15:05  数据源稳定
15:35  screener.py 跑(5-10 min)
15:40  HTML 渲染(10-30s)
15:45  brief.py 自动生成 top 10×2 策略(2-3 min)
15:50  全部就绪
16:00+ 你读 report.html → brief.py 深入 → AI 分析 → 决策 → log.py
```

### 缓存(三层)

| 层 | 路径 | TTL | 失效 |
|---|---|---|---|
| L1 em_get URL | `data/.cache/em/` | 15 min | `--force` |
| L2 brief 快照 | `data/screen/briefs/<code>/<date>.json` | 持久 | `--force` |
| L3 screener daily | `data/screen/daily/<date>/` | 持久 | `--force` |

### 磁盘预算

| 资产 | 年化 |
|---|---|
| OHLCV parquet | 50 MB(现有) |
| screener.sqlite | ~25 MB |
| decisions.sqlite | <100 KB |
| daily JSON | ~7.5 MB |
| briefs JSON | ~25 MB |
| **合计** | **~120 MB/年** |

### 失败恢复

| 故障 | 行为 | 恢复 |
|---|---|---|
| screener 全挂 | daily_summary.status='failed' | 手动 `--force` |
| HTML 渲染挂 | 数据在 SQLite,无 HTML | `--render-only` |
| brief 部分挂 | 单股失败 log,其他继续 | 手动 `brief.py <code>` |
| em_get 触发封禁 | 重试 3 次后跳过 | 等 5-30 分钟解封 |
| SQLite 损坏 | (极低) | `data/backup/` 恢复 |

---

## 10. 测试策略

### L1 单元测试(默认跑)
- `tests/test_a_screen_*`:业务逻辑,mock 数据层
- `tests/test_db.py`:schema/CRUD/UPSERT
- `tests/test_ohlcv.py`:parquet 读
- `tests/test_stats.py`:纪律性指标在 fixture 上的正确性

### L2 集成测试(默认 skip,`-m integration` 启用)
- `tests/integration/test_a_stock_data_smoke.py`:真发 1-2 端点
- `tests/integration/test_em_get_throttle.py`:验证 1.5s 间隔
- `tests/integration/test_screener_e2e.py`:单一 date 完整跑

### L3 冒烟(cron 部署前)
- `tests/smoke/run_daily.sh`:用最近交易日重跑,验证产物完整

### 验证清单

- 评分稳定:同日重跑排序一致
- 跨源对账:对 1-2 只股 PE/PB 跟 akshare 对比
- brief 完整:跑 20 只 brief,字段都非 null
- 纪律性合理:30%-80% 区间
- 胜率可解释:季度扫前 10 笔决策

---

## 11. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| a-stock-data 字段变 | 中 | 中 | 集成测试捕获 |
| 东财风控(海外) | 高 | 中 | em_get 限流 + cache + 重试 |
| moo tdx 误用 | 中 | 低 | 不 vendor,文档禁用 |
| SQLite 损坏 | 极低 | 高 | 周 backup 到 `data/backup/` |
| 评分 weights 主观 | 高 | 中 | 默认值 + config 集中 |
| 复盘失真(漏记) | 中 | 中 | 简化模式降低阻力,周报提示 |
| 决策不挂 brief | 中 | 低 | log.py 自动检测 brief |

---

## 12. 实施顺序

| Phase | 内容 | 估时 |
|---|---|---|
| 1 | a_stock_data/ vendor + db.py + ohlcv.py + schema 迁移 | 2-3 天 |
| 2 | a_screen/ 业务层 + 单元测试(mocked) | 2-3 天 |
| 3 | screener.py 入口 + E2E + smoke test | 2 天 |
| 4 | brief.py + snapshot + AI handoff 验证 | 2 天 |
| 5 | log.py + stats.py + 纪律性查询 | 2 天 |
| 6 | cron + 监控 + backup | 0.5 天 |

合计 ~2-3 周完成核心(Phase 1-5),Phase 6 半周收尾。

---

## 13. 关键决策汇总

| 决策 | 选择 | 理由 |
|---|---|---|
| 入口 | screener/brief/log/stats 四 CLI | 简单,可脚本化 |
| 存储 | SQLite × 2 + 文件 | schema 显式 + 快照可看 |
| 集成 | 11 必用 + 4 保留 = 15 端点 | 核心 + 偶尔 |
| 自动化 | cron 15:35 周末停 | <30 min/day 零操作 |
| AI | 脚本抓数据,对话中分析,写回 JSON | 不锁 LLM API |
| 测试 | 单元 + 集成 + 冒烟,分层 | mock 网络可控 |
| 数据/关系分离 | screener.sqlite vs decisions.sqlite | 增长速率不同,粒度独立 |
| 复盘 schema | 重量级(计划 + 实际) | 纪律性是核心反思维度 |
| 板块过滤 | 不预设,靠 ths_hot_reason + concept_blocks | 主动发现模式 |
| 现金/仓位 | 不入 DB,只记百分比 | 单一账户假设 |

---

## 14. 已知未定项

本设计有几处需要在实施时确认的细节(不阻塞实施):

1. **`tencent_quote` 重试 backoff**:1s 还是指数退避
2. **brief 自动生成的 top N**:暂定 10,可调
3. **em_get cache 淘汰策略**:TTL 还是 LRU
4. **discipline report 默认窗口**:近 30 天 / 近 90 天 / 全部
5. **WLB 数据源**:本设计没纳入,后续看是否需要(中线基本面)

实施时遇到具体场景再决定。
