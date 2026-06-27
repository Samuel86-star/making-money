# Project State — 2026-06-27

> 这是项目持久化状态, 每次会话开头读一遍。
> 任何工具/CI/子代理启动时都应加载。

## 角色

理财专家 (用户的唯一顾问)。不替下单, 推送后用户拍板。

## 目标

- 2026-12-31 前 78,788 → 100,000 (+26.9%)
- 6 个月, 11 个监控规则
- P(达成) 蒙特卡洛基线 = 0.1% (必须主动加仓)

## 当前持仓 (5 + 1 候选)

```
515650  消费50ETF      13,000  0.955   12,415
600276  恒瑞医药          200  48.67    9,734
300059  东方财富          300  20.07    6,021
159801  芯片ETF广发    2,000  1.547    3,094
159915  创业板ETF     2,700  4.215   11,380
─────────────────────────────────────────
股票/ETF 小计                    42,644
现金                             36,144
总资产                           78,788
```

候选: `515880 通信ETF` (周一14:30 后 ≤1.70 试仓 3000股)

## 工具链 (本周末新增)

```
a_stock/
├── goal_sim.py        蒙特卡洛
├── risk_metrics.py    组合风险
├── position_sizer.py  凯利公式
├── macro_calendar.py  宏观日历
├── notifier.py        Mac 推送 (osascript)
├── monitor.py         监控主循环
├── sentiment.py       情绪温度
├── rules.yaml         9 条监控规则
├── setup_cron.sh      安装 cron
└── MONITOR_README.md  完整文档
```

## 关键命令

```bash
cd /Users/maerun/Documents/Projects/make-money

# 跑一次
.venv/bin/python -m a_stock.goal_sim
.venv/bin/python -m a_stock.risk_metrics
.venv/bin/python -m a_stock.monitor --dry-run

# 加仓写入
.venv/bin/python -m a_stock.log add 515650 --strategy mid --price 0.95 --qty 7000

# 装 cron (周一自动监控)
./a_stock/setup_cron.sh install
```

## 当前最重要的 3 件事

1. **周一开盘前**: `./a_stock/setup_cron.sh install`
2. **测试 Mac 推送**: `.venv/bin/python -m a_stock.notifier test`
3. **确认触发阈值**: 看 `a_stock/rules.yaml`, 有问题就改

## 决策日志

- 2026-06-27 搭建 9 工具闭环 + cron 准备
