# 方法论审计 — 2026-06-30

> CFO梳理全部已实现方法论 + 冲突检查的基线。逐条修, 修完打✅。

## 已实现方法论 (4层)

- L1 铁律: docs/knowledge/ 01-04 (止损/技术/持仓/债)
- L2 借鉴6条: docs/references/trading-skills-methodology.md (Portfolio Heat/MFE-MAE/Expectancy/市场结构/VCP/Edge Pipeline)
- L3 代码工具: a_stock/*.py (risk_metrics/market_regime/mfe_mae/backtest_hypothesis/ohlcv/stats/monitor等)
- L4 假设验证: docs/review/daily.md [A]-[G] (严格5工作日回测)

## 修复清单

| 优先 | 项 | 状态 | 修复 |
|---|---|---|---|
| 🔴1 | Expectancy断链: setup列无人写入 | ✅ | insert_decision/add_buy/add_add加setup参数; log.py buy/add加--setup; expectancy实盘已能跑(5笔) |
| 🔴2 | 择时信号冲突无优先级 | ✅ | market_regime.posture(): 市场结构为锚+情绪为辅→offensive/neutral/defensive. SEVERE/HIGH→defensive |
| 🟡3 | 强势vs弱势入场框架未分清 | ✅ | knowledge/README加"入场框架"段: 弱势等支撑回踩, 强势形态确认即入(VCP+突破) |
| 🟡4 | scorer不联动market_regime | ✅ | morning_scan在SEVERE/HIGH过滤偏多股(实盘11→3) |
| 🟢5 | 止损体系4套层级未文档化 | ✅ | knowledge/README加"止损体系层级"段: rules.yaml硬触发>ATR计划止损>Heat汇总>MFE/MAE调参 |

## 验证
- 测试 192 passed (+7 audit修复) 0回归, T_污染0
- posture实盘: SEVERE+情绪30→defensive ✅; temp=100边界修复 (NORMAL+100→offensive, HIGH+100→defensive)
- morning_scan实盘: SEVERE白名单过滤追多股11→3 ✅
- expectancy实盘: 5笔已平仓能分组算 ✅
- insert_decision内置_migrate_setup_column: fresh部署不再crash ✅

## code-review round 2 修复 (5 findings)
- 🔴 insert_decision内置migration (fresh部署防crash)
- 🔴 posture temp=100边界 (<=100)
- 🟡 morning_scan改白名单过滤 (DEFENSIVE_LEVELS), top切片移到4b后
- 🟡 过滤计数修正 (filtered_out单独算)
- 🔵 _interactive_buy补setup输入

## 残留 (非阻塞)
- setup标签需新交易主动带 (--setup pullback/breakout/...), 旧5笔归"未分类". 攒够30笔带setup后backtest_hypothesis才有统计意义.
- posture目前是函数, 未自动驱动仓位. 后续可让monitor/close_scan输出posture提醒.
