# Project State — 2026-06-28

> 这是项目持久化状态, 每次会话开头读一遍。
> 任何工具/CI/子代理启动时都应加载。

## 角色

理财专家 (用户的唯一顾问)。不替下单, 推送后用户拍板。

## 目标

- 2026-12-31 前 78,788 → 100,000 (+26.9% / 185天)
- P(达成) 蒙特卡洛基线 = 0.2% (必须主动加仓+择时)
- 11 条监控规则(7条加仓/2条风控/2条止盈)
- 3 条调度任务(09:35早盘/09:50确认/15:10盘后/15:30OHLCV刷新)

## 当前持仓 (5)

```
600276  恒瑞医药          200  48.67    9,734
515650  消费50ETF     13,000  0.955   12,415
300059  东方财富          300  20.07    6,021
159801  芯片ETF广发    2,000  1.547    3,094
159915  创业板ETF      2,700  4.215   11,380
─────────────────────────────────────────
股票/ETF 小计                    42,644
现金                             36,144
总资产                           78,788
```

候选: `515880 通信ETF` (周一14:30 后 ≤1.70 试仓 3000股)

## 工具链 (已部署 2026-06-27)

```
a_stock/
├── monitor.py         每5分钟  价格规则+异动检测 (9-11/13-14/15:05)
├── scheduler.py       每分钟   多时间点调度 (morning_scan/close_scan)
├── notifier.py        Mac弹窗   (已测试通过)
├── morning_scan.py    09:35/50 全市场扫描→评分→推送候选
├── close_scan.py      15:10    盘后落盘 (板块/情绪/持仓评分)
├── sector_rotation.py          板块轮动持续性分析 (需≥2天历史)
├── sentiment.py                情绪温度计
├── scorers/                    多因子评分 (技术35%/资金35%/基本面10%/板块10%/事件10%)
├── screener.py                 全市场筛选 (东财push2)
├── anomaly.py                  火箭发射/高台跳水
├── goal_sim.py                 蒙特卡洛目标概率
├── risk_metrics.py             组合风险指标
├── position_sizer.py           凯利仓位计算
├── macro_calendar.py           宏观日历
├── rules.yaml                  11条监控规则
├── db.py                       DB schema + helpers
└── config.py                   配置
```

## cron 状态 (已安装) ## ✅

| 任务 | 频率 | 时段 | 说明 |
|---|---|---|---|
| monitor | 每5min | 9-11/13-14/15:05 | 价格规则+异动 |
| scheduler | 每分钟 | 9-15 | 09:35早盘速览→09:50早盘确认→15:10盘后落盘 |
| 日志 | - | - | `data/logs/{monitor,scheduler}.log` |

## 数据管道状态 (2026-06-27)

| DB | 状态 | 说明 |
|---|---|---|
| decisions.sqlite | ✅ 5真实持仓 | 600276/515650/300059/159801/159915 |
| sector_rotation.sqlite | ✅ 1天基线 | 2026-06-27 snapshot (20板块) |
| scheduler.sqlite | ✅ 3任务注册 | 09:35/09:50/15:10 |
| screener.sqlite | ⏳ 空 | 周一开盘自动填充 |
| watchlist | ✅ 3条 | 恒瑞/创业板ETF/通信ETF候选 |

**待积累:** sector_rotation/close_scan 需≥2交易日才产出趋势分析。周一开盘后自动填充。

## 周一自动流程

```
09:00   scheduler 启动 → 判断交易时段
09:35   morning_scan_1 → 东财push2拉全市场 → 多因子评分 → 推送top5候选
09:50   morning_scan_2 → 二次扫描确认 → 推送更新
09:35-11:30 每5min monitor → 检查11条价格规则 → 异动检测
13:00-15:00 每5min monitor → 下午盘规则检查
14:30   ← 通信ETF候选触发窗口 (≤1.70试仓3000股)
15:05   monitor → 尾盘检查
15:10   close_scan → 板块轮动snapshot + 情绪温度 + 持仓评分 → 落盘
```

## 关键命令

```bash
cd /Users/maerun/Projects/make-money

# 跑一次
.venv/bin/python -m a_stock.goal_sim
.venv/bin/python -m a_stock.risk_metrics
.venv/bin/python -m a_stock.monitor --dry-run
.venv/bin/python -m a_stock.scheduler session   # 当前交易时段

# 加仓写入
.venv/bin/python -m a_stock.log add 515650 --strategy mid --price 0.95 --qty 7000

# 每日复盘
.venv/bin/python -m a_stock.close_scan --dry-run
.venv/bin/python -m a_stock.sector_rotation analyze

# cron 管理
./a_stock/setup_cron.sh install|uninstall|status|test
```

## 当前最重要的 3 件事

1. **周一09:25** — 开盘前跑 `scheduler session` 确认交易时段
2. **周一14:30+** — 看515880通信ETF是否≤1.70, 触发则试仓3000股
3. **周一15:10后** — 跑 `close_scan` 看收盘评分 + `sector_rotation snapshot` 存板块基线

## 决策日志

- 2026-06-27 清测试数据 + 装cron + 测试管道 → 周一开盘自动运行
- 2026-06-27 周复盘: 芯片ETF评分最高(60.5偏多/+10.9%)中线最强; 消费50ETF RSI24.6超卖; 恒瑞/东财技术中性; 通信ETF候选距1.70买入线3.2%; 全市场候选人RSI>94超买需等回调. 新增OHLCV日刷新(15:30). P(达成100k)=0.2%, 需主动操作.
- 2026-06-28 strategies/ code-review 复核: #1/#3/#4/#5/#6/#7 真 bug 已修 (commit f85734b), #2 评分池设计如此不动. 测试 90 passed.
- 2026-06-28 agency-agents 评估复核: 纠正 2 误读 (Reality Checker=web QA, Risk Assessor=企业风控错配组合). 详见 `docs/references/agency-agents-assessment.md` 复核裁决段.
- 2026-06-28 P0 deep_research 论点破坏者 (thesis_breakers): 每个深研输出"什么情况下该撤" 5 维退出触发 (净利转负/ROE弱/PE过高/动量走坏/评分恶化). 顺手修 main() --skip-review 分支 UnboundLocalError. +11 测试.
- 2026-06-28 P1 risk_metrics 增强: Sortino 真实现 (修 FIXME, 用 parquet 日收益算下行波动) + 板块集中度 (classify_sector 6 板块) + 压力测试 (板块冲击/全市场暴跌). +17 测试. CLI 验证: 真实持仓最大单仓 29.1%, 板块分散, ✅ 风险可控.
- 2026-06-28 测试污染清理: 发现 tests/test_db.py 用真实代码 000858+生产DB 写库, 每跑一次污染 2 条, 累积 64 条. 删 66 条脏数据 (000858×64 + T_AA/T_BB×2). 修 3 测试文件隔离: test_db.py 改 tmp DB+T_前缀, test_decision_log/test_stats 加 teardown. 连续跑全套零残留. 详见 `code-review/2026-06-28-test-db-pollution.md`.
- 2026-06-28 测试: 118 passed 16 skipped (baseline 90 → +28: deep_research 11 + risk_metrics 17).
