# A股决策支持系统

> 个人A股投资者决策支持系统。脚本(cron)盯盘 → 命中规则 → Mac弹窗 → 用户下单。
> 角色: 理财顾问。不替下单, 不AI替判断, 决策权在用户。
> 目标: 2026-12-31 前 78,788 → 100,000 (+26.9%)。蒙特卡洛基线 P(达成)=0.2%, 需主动加仓+择时。

完整状态/持仓/工具见 `data/PROJECT_STATE.md` (每次会话开头读)。架构图见 `docs/architecture/system-architecture.md`。

## 能力分层

### 🔍 发现层 (找机会)
| 能力 | 模块 | 输出 |
|---|---|---|
| 全市场资金流扫描 | `screener` | 东财push2 拉全市场, 按净流入排名 topN |
| 5策略 Signal Bridge | `strategies/` | 趋势突破/超跌反弹/逼近涨停/资金流异动/板块动量 → 信号聚合 topM |
| 多因子评分 | `scorers/` | 技术35%+资金35%+基本面10%+板块10%+事件10% → 总分+否决 |
| 早盘扫描 | `morning_scan` | 09:35/09:50 策略候选∪screener top10 → 评分 → 推送top5 |
| 异动检测 | `anomaly` | 火箭发射(3min涨速>1%+量比>1.5)/高台跳水 |
| 板块轮动 | `sector_rotation` | 持续性分析, 4指标+资金流 (需≥2天历史) |

### ✅ 确认层 (验证机会)
| 能力 | 模块 | 输出 |
|---|---|---|
| 深度研究 | `deep_research` | DCF+Comps+DD清单+催化剂+论点破坏者 |
| 物理门禁 | `self_review` | 5 critical checks >0 → raise 阻断出建议 |
| 简报快照 | `a_screen/brief_builder` | 标的简报 snapshot |

### 📊 评分层 (5维量化打分)
技术面(MA60/RSI/新高/量比) · 资金面(净流入/大单) · 基本面(EPS/PE/ROE) · 板块(轮动领涨) · 事件(研报/龙虎榜/热度) → 总分 + 一票否决

### ⚡ 执行层 (盯盘+推送)
| 能力 | 模块 | 输出 |
|---|---|---|
| 价格规则监控 | `monitor` | 11条规则(7加仓/2风控/2止盈) 每5min |
| 异动监控 | `anomaly` | 持仓+候选 实时火箭/跳水 |
| Mac弹窗推送 | `notifier` | osascript + RateLimiter三闸门(20条/min/0.5s/错误锁) |
| 凯利仓位 | `position_sizer` | 凯利公式算仓位% |
| 决策记录 | `log` | buy/add/close/reduce/plan/watchlist 写DB |

### 📈 复盘层 (回顾+风控)
| 能力 | 模块 | 输出 |
|---|---|---|
| 盘后落盘 | `close_scan` | 15:10 板块snapshot+情绪+持仓评分 |
| 情绪温度计 | `sentiment` | 北向+龙虎榜+研报热度 0-100 |
| 蒙特卡洛目标 | `goal_sim` | P(达成100k) 概率 |
| 组合风险 | `risk_metrics` | Sharpe/Sortino/VaR/MaxDD/HHI/板块集中度/压力测试 |
| 交易统计 | `stats` | 胜率/纪律分析 |

### ⏰ 调度层
| 能力 | 模块 | 输出 |
|---|---|---|
| 多时间点调度 | `scheduler` | 09:35/09:50/15:10/15:30, 6段时段, 节假日识别 |
| cron 集成 | `setup_cron.sh` | monitor 5min + scheduler 每分钟 |

### 🛠 辅助
- 宏观日历 `macro_calendar` (FOMC/政治局会议/财报季)
- 待办系统 `todo`
- OHLCV加载 `ohlcv` (K线parquet)

## 数据源
| 数据源 | 用途 |
|---|---|
| 东财 push2 | 资金流/板块/龙虎榜/研报 |
| 腾讯 qt.gtimg.cn | 实时报价 (monitor主力) |
| 同花顺 | 热度/EPS/北向 |
| 新浪财报 | 三表/公告 |
| OHLCV parquet | K线/技术指标 |

## CLI 入口

所有 CLI 走 `python -m`, 用项目 `.venv`:

```bash
# 盯盘/调度
.venv/bin/python -m a_stock.monitor --dry-run     # 监控dry-run
.venv/bin/python -m a_stock.scheduler session     # 当前交易时段
.venv/bin/python -m a_stock.morning_scan --dry-run
.venv/bin/python -m a_stock.close_scan --dry-run

# 研究/风控
.venv/bin/python -m a_stock.deep_research 600276 --json   # 深研(含论点破坏者)
.venv/bin/python -m a_stock.risk_metrics                  # 组合风险(含压力测试)
.venv/bin/python -m a_stock.goal_sim                      # 蒙特卡洛
.venv/bin/python -m a_stock.position_sizer 600276         # 凯利仓位
.venv/bin/python -m a_stock.sentiment                     # 情绪温度

# 决策记录
.venv/bin/python -m a_stock.log buy 515650 --strategy mid --price 0.95 --qty 7000
.venv/bin/python -m a_stock.log add 515650 --strategy mid --price 0.95 --qty 7000
.venv/bin/python -m a_stock.log close 1 --close-date 2026-07-01 --close-price 11 --close-reason target
.venv/bin/python -m a_stock.log list --open

# 复盘/辅助
.venv/bin/python -m a_stock.stats                       # 交易统计
.venv/bin/python -m a_stock.sector_rotation analyze     # 板块轮动
.venv/bin/python -m a_stock.macro_calendar list         # 宏观日历
.venv/bin/python -m a_stock.todo list                   # 待办

# cron 管理
./a_stock/setup_cron.sh install|uninstall|status|test
```

## 项目结构

```
a_stock/
├── monitor.py          每5min 价格规则+异动检测
├── scheduler.py        每min 多时间点调度 (早盘/盘后)
├── notifier.py         Mac弹窗 (RateLimiter三闸门)
├── morning_scan.py     09:35/50 全市场扫描→策略→评分→推送
├── close_scan.py       15:10 盘后落盘
├── anomaly.py          火箭发射/高台跳水
├── sector_rotation.py  板块轮动持续性
├── sentiment.py        情绪温度计
├── self_review.py      物理门禁 (critical>0 阻断)
├── deep_research.py    DCF+Comps+DD+论点破坏者
├── goal_sim.py         蒙特卡洛目标概率
├── risk_metrics.py     组合风险 (Sharpe/Sortino/压力测试)
├── position_sizer.py   凯利仓位
├── macro_calendar.py   宏观日历
├── screener.py         全市场筛选 (东财push2)
├── ohlcv.py            OHLCV加载
├── log.py / stats.py / todo.py   决策/统计/待办 CLI
├── config.py / db.py   配置 / DB schema
├── rules.yaml          11条监控规则
├── setup_cron.sh       cron安装
├── scorers/            多因子评分 (5维)
├── strategies/         5策略 Signal Bridge
├── a_screen/           筛选/简报/决策日志
└── a_stock_data/       数据源层 (东财/腾讯/同花顺/新浪)
```

## 存储 (data/)
- `decisions.sqlite` — 决策日志/持仓/资金曲线
- `screener.sqlite` — 全市场扫描/daily_close
- `scheduler.sqlite` — 调度持久化 (WAL)
- `anomaly_ticks.sqlite` — tick缓存 3天
- `sector_rotation.sqlite` — 板块轮动历史
- 4个JSON状态文件 (monitor/sentiment/self_review/todo)

## 测试

```bash
.venv/bin/python -m pytest tests/ -q          # 单元测试 (无网络)
.venv/bin/python -m pytest tests/ --run-integration -v   # 含集成测试 (需网络)
```

测试隔离: DB 写入用 tmp DB 或 T_ 前缀 + teardown 清理, 不污染生产 `decisions.sqlite`。

## cron 调度 (已安装)

| 任务 | 频率 | 时段 | 说明 |
|---|---|---|---|
| monitor | 每5min | 9-11/13-14/15:05 | 价格规则+异动 |
| scheduler | 每1min | 9-15 | 09:35早盘→09:50确认→15:10盘后→15:30 OHLCV刷新 |

## 明确不具备的能力
- ❌ 自动下单 (设计如此, 仅弹窗, 决策权在用户)
- ❌ 卖方共识数据 (无数据源)
- ❌ ESG/供应链风控 (错配个人组合)
- ❌ 回测框架 / 多券商对接 / Level-2盘口 / 期权衍生品

## 附属项目
- `analysis/technology/` — AI算力产业链 / HBM国产化设备链 可视化 (独立HTML, 无依赖)

---

> **免责声明:** 本项目仅供个人研究教育, 不构成投资建议。
