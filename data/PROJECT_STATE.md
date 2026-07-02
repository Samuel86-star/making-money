# Project State — 2026-07-01

> 这是项目持久化状态, 每次会话开头读一遍。
> 任何工具/CI/子代理启动时都应加载。

## 角色

理财专家 (用户的唯一顾问)。不替下单, 推送后用户拍板。

## 目标

- 2026-12-31 前 78,788 → 100,000 (+26.9% / 184天剩)
- P(达成) 蒙特卡洛基线 = 0.2% (必须主动加仓+择时)
- 13 条监控规则 (06-29 加 159915 ATR止损+护栏 / 159516 回踩提醒)
- 3 条调度任务 (09:35早盘/09:50确认/15:10盘后/15:30OHLCV刷新)

## 当前持仓 (5) — 口径 2026-06-29 收盘

> 07-01 现价 API 不可达 (push2/腾讯全空), 市值列暂用 06-29 收盘。
> 下交易日盘前 `log cost` + 行情刷新后回写。06-30 起无交易 (db 确认)。

```
600276  恒瑞医药        100  49.121    5,293   已实现+355
515650  消费50ETF    13000   0.981   12,753   已实现+0
300059  东方财富        100  21.279    2,010   已实现-246
159801  芯片ETF广发     200   1.541      327   已实现+77
159915  创业板ETF      1000   4.215    4,236   已实现-119
─────────────────────────────────────────────
股票/ETF 小计                    24,619   已实现合计 +67
现金                             55,319
总资产 (06-29收盘)               79,938   进度 79.9% → 100k
```

候选/观察 (非持仓):
- `159516 半导体材料设备ETF` — 07-01 Turtle sys2 突破 (入场1.762/止损1.574/1Unit4200股), 待回踩或突破确认
- `515880 通信ETF` — 06-30 死等1.70踏空 (+4.72%错过~201元), 教训 [A]: 强势票不死等深回踩

## 工具链 (2026-07-01 增强版)

```
a_stock/
├── monitor.py         每5分钟  价格规则+异动检测 (9-11/13-14/15:05)
├── scheduler.py       每分钟   多时间点调度 (morning_scan/close_scan)
├── notifier.py        Mac弹窗
├── morning_scan.py    09:35/50 全市场扫描→评分→推送候选 (存candidate_history)
├── close_scan.py      15:10    盘后落盘 (板块/情绪/持仓评分/industry_flow)
├── sector_rotation.py          板块轮动持续性
├── sentiment.py                情绪温度计
├── market_regime.py            市场结构 (派发日+FTD, 风险等级)  [P0]
├── mfe_mae.py                  持仓过程极值
├── turtle.py                   ★新: Donchian突破+2N止损+1%Unit+4Unit金字塔 [P2]
├── scorers/                    多因子评分 (技术35%/资金35%/基本面10%/板块10%/事件10%)
│   ├── technical_scorer.py     ★强: MA/MACD/RSI + 量价 + VCP(Minervini) + Wyckoff派发/吸筹
│   ├── moneyflow_scorer.py     ★强: main分档 + 超大单 + 资金加速 + 量价背离(个股[J])
│   ├── fundamental_scorer.py
│   ├── sector_scorer.py
│   └── event_scorer.py
├── screener.py                 全市场筛选 (东财push2)
├── anomaly.py                  火箭发射/高台跳水
├── goal_sim.py                 蒙特卡洛目标概率
├── risk_metrics.py             组合风险 (Portfolio Heat/Sortino/板块冲击)
├── position_sizer.py           凯利+固定风险+R倍数(Van Tharp), setup→backtested Kelly [P1]
├── setup_registry.py           ★新: edge库, 8setup expectancy+Kelly (验证→sizing)
├── signal_backtest.py          ★新: 历史回测detector edge, 止损建模, confluence, pairs
├── edge_scanner.py             ★新: 验证setup→今天买什么 (sized候选, 扣成本)
├── deep_research.py            DCF+Comps深研 (含 thesis_breakers)
├── backtest_hypothesis.py      技能假设回测 (满5工作日)
├── macro_calendar.py           宏观日历
├── log.py                      决策记录 (含 cost 子命令)
├── rules.yaml                  13条监控规则
├── db.py / config.py / ohlcv.py (atr/struct_stop_loss/vcp_score)
└── a_stock_data/               东财push2/腾讯/同花顺/新浪财报
```

## Edge 库 / 验证交易框架 (2026-07-02)

> 18 commits 信号验证体系的核心结论. 全部数据驱动 (5165只parquet历史回测).
> 详 `docs/review/signal_validation.md`. 老板焦虑P(达成)=0.2%的量化进攻路径.

### 8 Setup 期望+Kelly 排名 (5%止损/10d/扣0.3%成本前)

| setup | n | 胜率 | 赔率 | 期望/笔 | 半Kelly |
|---|---|---|---|---|---|
| **★sys1+Wyckoff吸筹** | 9000 | 47.2% | 1.99 | **+1.75%** | **10.3%** |
| Turtle sys1 | 41071 | 42.3% | 2.04 | +1.22% | 7.0% |
| sys1+VCP | 1363 | 31.6% | 2.82 | +0.97% | 3.6% |
| Turtle sys2 | 45037 | 28.4% | 3.11 | +0.80% | 2.7% |
| VCP突破 | 4470 | 30.1% | 2.84 | +0.74% | 2.7% |
| Wyckoff吸筹 | 98751 | 37.9% | 2.07 | +0.72% | 3.9% |
| Wyckoff派发(回避) | 86514 | 37.9% | 1.80 | +0.26% | 1.7% |

### 验证硬结论 (改认知)

| 维度 | 验证前 | 验证后 |
|---|---|---|
| VCP | 强化[A]主力 | 旧版无edge→加突破确认→modest正edge |
| 止损 | 越紧越安全 | **3%=自残, 5%甜区** (实证铁律) |
| 信号叠加 | 越多越好 | **恰好2信号最强, 3+失效** |
| 单信号 | 各有edge | 多数≈base, 别重仓 |
| sys2量过滤 | 量确认更稳 | **量确认毁sys2 edge** (拥挤交易) |
| confluence来源 | 未拆 | **Turtle+Wyckoff对强, 含VCP对弱** |

### 可倚交易框架 (实战部署)

- **主推setup**: Turtle sys1 + Wyckoff吸筹 同日触发 (期望+1.75%/笔, 半Kelly 10%)
- **止损**: 5% (3%自残, 实证)
- **仓位**: 半Kelly, backtested参数 (position_sizer setup=)
- **回避**: Wyckoff派发股, VCP单信号不重仓, 3+信号过热
- **部署**: 69%现金分批, ~10%/笔, 2-3并发=20-30%新增, 总50-60%

### 闭环工具链

```
morning_scan(选股+5信号+confluence) → signal_backtest(验证edge)
→ setup_registry(8setup expectancy+Kelly) → detect_setup(命中)
→ position_sizer(backtested Kelly) → edge_scanner(今天买什么, 扣成本)
```

### 关键命令

```bash
.venv/bin/python -m a_stock.signal_backtest --stop 5      # 信号edge (止损建模)
.venv/bin/python -m a_stock.signal_backtest --confluence   # 2信号叠加
.venv/bin/python -m a_stock.signal_backtest --pairs        # 子组合拆解
.venv/bin/python -m a_stock.setup_registry                 # edge库 (Kelly仓位)
.venv/bin/python -m a_stock.edge_scanner --top 15          # 今天买什么 (sized)
```

### 诚实局限

- **涨市数据** (base rate正), 跌市表现未知 — 真考验待跌市样本
- 交易成本0.3%/笔已扣 (edge_scanner/setup_registry净期望)
- 假设[A]-[J] 07-06/07-07/07-08 日记回测仍待 (需交易日, 独立于detector验证)
- 幸存者偏差 (parquet无退市, A股81-244日窗口小)


## cron 状态 ✅ (已安装)

| 任务 | 频率 | 时段 | 说明 |
|---|---|---|---|
| monitor | 每5min | 9-11/13-14/15:05 | 价格规则+异动 |
| scheduler | 每分钟 | 9-15 | 09:35早盘速览→09:50确认→15:10盘后 |
| 日志 | - | - | `data/logs/{monitor,scheduler}.log` |

## 数据管道状态 (2026-07-01)

| DB | 状态 | 说明 |
|---|---|---|
| decisions.sqlite | ✅ 5真实持仓 | 600276/515650/300059/159801/159915 (06-30起无交易) |
| sector_rotation.sqlite | ✅ | close_scan 每日落盘 |
| scheduler.sqlite | ✅ 3任务 | 09:35/09:50/15:10 |
| candidate_history | ✅ 新 | morning_scan 持久化, 解 [A][B][C] 回测数据源 |
| industry_flow | ✅ | close_scan 拉, 失败重试+告警 (解 [J] 数据缺口) |
| ohlcv parquet | ✅ | ETF~81日 / 600276 244日 (07-01 push2空, 待刷新) |

## 交易日自动流程

```
09:00   scheduler 启动 → 判断交易时段
09:25   跑盘前 checklist (docs/knowledge/pre_market_checklist.md)
09:35   morning_scan_1 → 东财push2拉全市场 → 多因子评分(含VCP/Wyckoff/super_zhuan) → 推送top5
09:50   morning_scan_2 → 二次确认 → 推送更新
09:35-15:00 每5min monitor → 13条价格规则 + 异动
15:05   monitor → 尾盘
15:10   close_scan → 板块/情绪/持仓评分/industry_flow 落盘
15:30   OHLCV 日刷新
```

## 关键命令

```bash
cd /Users/maerun/Projects/make-money

# 盘前/盘后
.venv/bin/python -m a_stock.scheduler session       # 当前交易时段
.venv/bin/python -m a_stock.morning_scan            # 扫描候选
.venv/bin/python -m a_stock.close_scan --dry-run    # 盘后复盘
.venv/bin/python -m a_stock.sentiment               # 情绪温度
.venv/bin/python -m a_stock.market_regime           # 派发日/风险等级
.venv/bin/python -m a_stock.turtle                  # ★Turtle突破信号 (持仓+候选)

# 持仓/成本
.venv/bin/python -m a_stock.log cost 600276         # 真实成本 (报盈亏前必查)
.venv/bin/python -m a_stock.risk_metrics            # 组合风险+Portfolio Heat
.venv/bin/python -m a_stock.position_sizer --method fixed  # R倍数仓位
.venv/bin/python -m a_stock.mfe_mae --update        # 持仓极值

# 回测/目标
.venv/bin/python -m a_stock.goal_sim                # 蒙特卡洛
.venv/bin/python -m a_stock.backtest_hypothesis --setup pullback  # 假设回测

# 监控/cron
.venv/bin/python -m a_stock.monitor --dry-run
./a_stock/setup_cron.sh install|uninstall|status|test
```

## 当前最重要的 3 件事

1. **下交易日盘前** — 跑 `edge_scanner --top 15` 看 sys1+Wyckoff吸筹 候选 + `morning_scan` 验证新因子实战. 体系首战.
2. **PROJECT_STATE 资产回写** — 07-01 push2/腾讯 API 全空, 市值仍 06-29 口径; 盘前 `log cost` + 行情刷新后更新总资产
3. **假设回测到点判定** — [D][E][F][G] 07-06 / [A][B][C] 07-07 / [J] 07-08 满 5 工作日, 跑 `backtest_hypothesis` (日记setup层, 区别detector层已验)

## 决策日志

- 2026-07-02 **验证→sizing闭环体系建成** (18 commits): signal_backtest(历史edge) → VCP修正(加突破确认) → 止损建模(3%自残/5%甜区, 实证铁律) → confluence(2信号最强+1.53%) → pairs拆解(sys1+Wyckoff吸筹workhorse) → setup_registry(8setup Kelly) → position_sizer接backtested Kelly → edge_scanner(今天买什么, 扣成本). 主推setup: sys1+Wyckoff吸筹 (期望+1.75%/笔, 半Kelly10%). 老板P(达成)=0.2%有完整量化进攻路径. 全套307 passed. 详 signal_validation.md + PROJECT_STATE "Edge库" 节.

- 2026-06-29 清测试数据 + 装cron + 测试管道 → 周一开盘自动运行
- 2026-06-29 首个交易日实战: 总资产 78,788→79,938 (+1,150/+1.46%, 进度79.9%). 已实现+67 (恒瑞52.67减100锁+355主功, 芯片1.615/1.545两次减仓锁+77, 创业板4.145浅止损-119, 东财20.05减200亏-246). 浮盈+303. 现金69%弹药充足.
- 2026-06-29 教训(老板扛): 上午盘面吓到, 创业板4.145浅止损割在日内低点, 芯片1.545第二刀偏早, 下午V回踏空~224元. 铁律固化: ETF止损≥3%或破前日低禁<2%, 强势板块减仓留底仓≥30%, 不在日内低点卖.
- 2026-06-29 持仓变更: 600276 200→100, 159801 2000→200, 159915 2700→1000, 300059 300→100, 515650 不变13000.
- 2026-06-29 CFO技能补课: 产出 docs/knowledge/ 01交易执行/02技术分析/03持仓管理与成本核算 + README铁律. 7项增强全部落地 (162 passed): technical_scorer量价验证 / log.py cost子命令 / rules.yaml改159915 ATR止损 / risk_metrics成本基 / validate_state校验 / ohlcv atr / 补拉159516.
- 2026-06-30 首个完整交易日复盘: 创业板+3.02% (4.364), 06-29割4.145踏空0.22/股. 515880死等1.70踏空+4.72%. 提出假设 [A]强势入场不死等深回踩 / [B]资金流surge+已涨>5%不追 / [C]scorer高位股失效. 详 daily.md.
- 2026-07-01 学习路径规划 + 假设回测数据源就绪: morning_scan 存 candidate_history (解[A][B][C]数据源), close_scan industry_flow 重试+告警 (解[J]).
- 2026-07-01 [J] 假设全天印证: 硬科技资金流出 (电子-545亿/半导体-260亿/通信-224亿), 出货信号明确. 待 07-08 正式回测.
- 2026-07-01 学习路径 P1+P2 全部代码项落地 (4 commits):
  - P1: VCP(Minervini)量化进 technical_scorer (全市场1.1%命中) + R倍数(Van Tharp)进 position_sizer
  - P2: Wyckoff派发/吸筹进 technical_scorer (UTAD 1.52%/Spring 0.10%严选) + Turtle突破系统新模块 turtle.py (159516 sys2突破量化印证) + 个股资金流super_zhuan进 moneyflow_scorer (超大单/加速/量价背离)
  - 全套 243 passed, 0 回归. 字段语义交易日自检测试 (main≈super+big) 待下交易日验.
