# 交易技能方法论借鉴 (claude-trading-skills)

> 来源: https://github.com/tradermonty/claude-trading-skills (60+ skills, 美股体系)
> 提炼: 6 条市场无关、可迁移到A股的方法论。美股专用(数据源/税务/期权)已剔除。
> 目的: 学后落地进代码, 强化100k目标的择时/风控/复盘能力。每条标注落地点。

---

## 1. Portfolio Heat (组合总风险敞口)

**原skill**: position-sizer / exposure-coach
**核心**: 总持仓风险 = Σ(每笔仓位 × 入场到止损的距离)。不是单仓%, 是**全部未平仓位的总下行风险**。设heat上限(如总资产6%)。
**我们缺**: risk_metrics有单仓%和集中度, 但没汇总"若全触及止损总亏多少"。
**A股落地**: `risk_metrics.py` 加 `portfolio_heat(positions)` = Σ (cost - stop) × qty。stop取db的plan_stop_loss, 缺则用ATR结构止损。输出heat元数+占总资产%。超6%报警。
**保护100k下行**: 直接量化"最坏情况亏多少"。

---

## 2. MFE/MAE (最大有利/不利偏移)

**原skill**: stockbee-setup-fluency-trainer
**核心**: 每笔交易记 MFE(入场后最大浮盈) + MAE(入场后最大浮亏)。按setup类型统计 → 回答"止损设多宽才不被洗"。
**我们缺**: daily.md复盘只记结果, 不记过程极值。无法验证[D]假设(ATR止损宽度)是否合理。
**A股落地**: monitor.py每5min tick更新各持仓的mfe/mae进state文件; log.py加`mfe`子命令报告; 平仓时记入decisions。
**验证[D]**: 攒样本后看MAE分布, 若止损宽度<常见MAE → 止损太窄被洗。

---

## 3. Expectancy by Setup (按setup分类期望值)

**原skill**: signal-postmortem / trade-performance-coach
**核心**: expectancy = 胜率×平均盈 − 败率×平均亏。按setup类型(回踩/突破/异动/规则)分别算, 才知道哪种setup该继续用。
**我们缺**: 复盘是叙事型, 无expectancy量化。不知"回踩买点"历史期望值。
**A股落地**: decisions加`setup`字段(migration); stats.py加`expectancy(by_setup=True)`。验证区[A][B][C]假设用这个判。
**决策依据**: expectancy<0的setup停用, >0的加仓。

---

## 4. Distribution Day + FTD (市场顶/底结构)

**原skill**: ibd-distribution-day-monitor / ftd-detector (O'Neil派)
**核心**:
- 派发日 = 指数收盘跌≥0.2%且放量。累积4-5个=市场见顶信号。
- FTD (Follow-Through Day) = 跌势后第4-7天出现放量涨≥1.5%, 确认反弹启动。
**我们缺**: sentiment温度(30谨慎)不够灵敏(今天30却组合+0.43%)。无市场顶/底结构识别。
**A股落地**: 新模块`market_regime.py`。读指数OHLCV(创业板ETF/沪深300), 算distribution day计数+FTD信号。输出风险等级 NORMAL/CAUTION/HIGH/SEVERE。
**比情绪温度硬**: 结构信号 > 模糊温度。

---

## 5. VCP (波动收缩形态)

**原skill**: vcp-screener (Minervini)
**核心**: Volatility Contraction Pattern — 洗盘时波动越缩越紧(连续几波收缩), 量缩, 突破前放量=买点。形态就绪度识别。
**我们缺**: morning_scan用多因子评分, 无"形态就绪度"。今天515880强势没上车部分因没识别VCP收缩完毕。
**A股落地**: ohlcv.py加`vcp_score(df)` — 检测连续N波波动收缩+量缩。screener/morning_scan调用, VCP高分=突破在即。
**呼应[A]假设**: VCP收缩完毕=强势形态确认入场点。

---

## 6. Edge Pipeline (假设→回测→reviewer)

**原skill**: edge-hint-extractor / backtest-expert / edge-strategy-reviewer
**核心**: 假设→回测→reviewer挑过拟合/样本不足/执行真实性。reviewer确定性打分。
**我们缺**: [A][B][C]假设验证是手写流程, 无"过拟合检测/样本量充分性/walk-forward"框架。
**A股落地**: 新CLI `backtest_hypothesis.py` — 输入setup+日期范围, 算命中率/expectancy, 输出样本量是否充分(n≥30?) + 过拟合警告。喂给daily.md验证区5工作日回测。
**强化复盘流程**: 让5日回测有硬框架, 非拍脑袋。

---

## 落地优先级 (对100k价值)

| 优先 | 方法论 | 落地点 | 验证假设 |
|---|---|---|---|
| 🔴 | Portfolio Heat | risk_metrics | 保护下行 |
| 🔴 | Distribution Day | market_regime (新) | 市场择时 |
| 🟡 | MFE/MAE | monitor + log | [D]止损宽度 |
| 🟡 | VCP | ohlcv + screener | [A]强势入场 |
| 🟢 | Expectancy | stats + decisions migration | [A][B][C] |
| 🟢 | Edge Pipeline | backtest_hypothesis (新) | 复盘框架 |

> 美股专用已剔除: finviz/alpaca/13F数据源、kanchi税务/股息、options/pair-trade、bubble-detector(太宏观)。
