# 未来增强清单 (Backlog)

> 汇总散落在各处的"待落地/待验证/后续可做"项, 避免丢失。按状态分类。
> 优先级: 🔴高(直接服务100k目标) / 🟡中 / 🟢低
> 状态: 💡设想 / 📋待验证(走5工作日backtest) / 🔨待开发 / ✅已完成

---

## A. 假设验证类 (走 backtest_hypothesis, 严格5工作日)

> 提出后在 daily.md 记 [编号], 满5工作日用 backtest_hypothesis --setup 验证, 命中固化进 rules/score, 不命中删。

| 编号 | 假设 | 提出 | 首次可回测日 | 状态 |
|---|---|---|---|---|
| [A] | 强势板块形态确认入场, 不死等深回踩 | 06-30 | 07-07 | 📋待验证 |
| [B] | 资金流surge+已涨>5%不追 | 06-30 | 07-07 | 📋待验证 (有反例) |
| [C] | scorer"观望偏多"对高位股失效 | 06-30 | 07-07 | 📋待验证 |
| [D] | ETF止损<2%是数学bug, 用ATR/结构位 | 06-29 | 07-06 | 📋待验证 (已先用) |
| [E] | 减在急拉不减在回踩, 强势留底仓≥30% | 06-29 | 07-06 | 📋待验证 (已先用) |
| [F] | 不在09:30-10:00减仓, 不在日内低点卖 | 06-29 | 07-06 | 📋待验证 (已先用) |
| [G] | 报盈亏前必查db成本不瞎猜 | 06-29 | 07-06 | 📋待验证 (已先用) |
| [H] | 低ROE+弹性拐点选股有效 (郑希视角1) | 07-01 | 待提出 | 💡设想, 待[A]-[G]验证后提 |
| [I] | 机构持仓变化/明星经理边际是有效资金面因子 (郑希视角4) | 07-01 | 待提出 | 💡设想, 需先接数据源 |

---

## B. 代码增强类 (待开发)

### 🔴 posture 自动驱动仓位 (audit残留)
- 现状: `market_regime.posture()` 是函数, 未自动输出
- 待做: monitor/close_scan 输出 posture 提醒 (offensive/neutral/defensive)
- 价值: 把择时信号优先级自动接入盯盘, 不靠人工判断
- 落点: monitor.py + close_scan.py

### 🟡 institutional_scorer.py (机构持仓因子)
- 现状: 仅方法论 (selection-perspectives.md 第4条), 无数据源
- 待做: 接基金季报/天天基金/东财基金持仓接口, 算 institutional_score
  `+基金持仓比例上升 +明星经理新进/加仓 +多机构共识但不拥挤 −单一基金过度集中 −明星经理减仓`
- 价值: 补中线资金面因子, A股机构抱团明显
- 边界: 中线/deep_research 用, 不适合日内 (季报滞后1月)

### 🟡 fundamental_scorer 加 roe_inflection 因子
- 现状: 仅方法论 (selection-perspectives.md 第1条)
- 待做: 加 `roe_inflection` = ROE低(<8%) + R&D/营收>5% + 营收环比加速
- 价值: 补黑马视角, 现有偏白马
- 前置: [H]假设验证通过

### 🟡 market_regime FTD 跌势检测改进
- 现状: FTD 用"连续2日跌"启发式, O'Neil原义是"指数从峰跌X%"
- 待做: 改为从近期高点回撤阈值检测跌势启动
- 价值: 避免漏检"先平后连跌"走势, FTD延迟识别
- 落点: market_regime.py ftd_signal

### 🟢 VCP 接入 morning_scan
- 现状: ohlcv.vcp_score 已实现, 未被 morning_scan 调用
- 待做: morning_scan 候选加 VCP 维度, 高分=突破在即
- 价值: 呼应[A]强势入场假设

### 🟢 MFE/MAE 平仓写入 decisions
- 现状: mfe_mae 累积中, 平仓时未持久化
- 待做: reduce/close 时把 mfe/mae 写入 decisions (新列或 reason)
- 价值: 攒样本验证[D]止损宽度, 不丢历史极值

---

## C. 数据/工具类

### 🟡 接全球利率/CPI/LPR 实时数据
- 现状: 沙箱WebSearch受限, 04-债券利率方向技能.md 框架可信但无精确数字
- 待做: 本地脚本拉国统局CPI / 央行LPR / 中美国债收益率 / CME FedWatch
- 价值: 补债框架定量, macro_calendar 增强
- 落点: 新建 macro_data.py 或扩 macro_calendar.py

### 🟢 补 159516 等候选 parquet
- 现状: 159516 已补, 但其他候选(515950等)无parquet
- 待做: 候选标的自动补拉 parquet
- 价值: 技术分析/VCP/market_regime 需 OHLCV

### 🟢 setup 标签历史回填
- 现状: 旧5笔已平仓 setup=NULL (未分类), expectancy 归"未分类"
- 待做: 手动回填历史交易的 setup 标签
- 价值: backtest_hypothesis 样本量↑

---

## D. 流程类

### ✅ 收盘复盘流程 (已落地)
- CLAUDE.md 固化, daily.md 累积, 严格5工作日回测

### ✅ Portfolio Heat / MFE-MAE / market_regime / VCP / expectancy / backtest_hypothesis (已落地)
- 6条借鉴方法论已落代码 + audit修复

### 🟡 daily.md 自动化
- 现状: 手动写
- 待做: close_scan 自动生成 daily.md 骨架 (行情/触发位/Heat 自动填, 教训人工补)
- 价值: 减少复盘手动工作量

---

## 维护说明
- 完成项移到对应"已落地"区或删除
- 新设想先记这里 + 提假设编号, 别直接写代码
- 每周一/月初回顾, 调优先级
