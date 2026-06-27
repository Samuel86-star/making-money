# A股投资决策系统 v0.5

理财专家工作流。从 7.88万 到 10万，6 个月目标。

## 一、目标与现状

```
总资产:    78,788 元
目标:      100,000 元
缺口:      +21,212 元 (+26.9%)
剩余:      185 天 (到 2026-12-31)
```

当前持仓: 5 只 (恒瑞/消费ETF/创业板/芯片/东财) + 1 候选 (通信ETF)

## 二、工具链

```
a_stock/
├── monitor.py         主监控循环 (价格规则+异动)
├── scheduler.py       多时间点调度 (早盘/盘后)
├── notifier.py        Mac 推送
│
├── morning_scan.py    早盘扫描 09:35/09:50
├── close_scan.py      盘后落盘 15:10
├── anomaly.py         火箭发射/高台跳水
├── sector_rotation.py 板块轮动持续性
├── sentiment.py       情绪温度 0-100
├── self_review.py     门禁系统
│
├── goal_sim.py        蒙特卡洛
├── risk_metrics.py    组合风险
├── position_sizer.py  凯利公式
├── deep_research.py   DCF+Comps深研
├── macro_calendar.py  宏观日历
├── log.py             决策记录
│
├── config.py          配置
├── db.py              DB schema
├── rules.yaml         监控规则
├── setup_cron.sh      Cron安装
│
├── scorers/           多因子评分 (技术35%/资金35%/基本面10%/板块10%/事件10%)
└── a_stock_data/      数据源层
```

## 三、运行命令

```bash
# 1. 看 P(达成目标)
.venv/bin/python -m a_stock.goal_sim

# 2. 看组合风险
.venv/bin/python -m a_stock.risk_metrics

# 3. 算每个标的建议仓位
.venv/bin/python -m a_stock.position_sizer --method kelly

# 4. 看情绪温度
.venv/bin/python -m a_stock.sentiment

# 5. 看宏观日历
.venv/bin/python -m a_stock.macro_calendar list

# 6. 手动跑一次监控 (不推不写)
.venv/bin/python -m a_stock.monitor --dry-run

# 7. 测试 Mac 推送
.venv/bin/python -m a_stock.notifier test

# 8. 安装 cron (自动监控)
./a_stock/setup_cron.sh install

# 9. 查看 cron 状态
./a_stock/setup_cron.sh status

# 10. 卸载 cron
./a_stock/setup_cron.sh uninstall
```

## 四、监控规则说明

`a_stock/rules.yaml` 9 条规则:

| 规则 | 触发条件 | 行动 | 频次限制 |
|---|---|---|---|
| 消费ETF加仓-1 | 价格 ≤ 0.95 | add 7000股 | 1/天 |
| 消费ETF加仓-2 | 价格 ≤ 0.93 | add 3000股 | 1/天 |
| 恒瑞加仓 | 价格 47-48 | add 100股 | 1/天 |
| 通信ETF试仓 | 价格 ≤ 1.70 + 周一14:30后 | add 3000股 | 1/天 |
| 通信ETF加码 | 价格 ≤ 1.60 | add 2000股 | 1/天 |
| 单标的日内-7% | 任一持仓 change_pct ≤ -7 | info 紧急 | 3/天 |
| 组合日内-3% | portfolio_change ≤ -3 | info 警告 | 2/天 |
| 创业板止盈 | 159915 ≤ 4.00 | reduce 1000股 | 1/天 |
| 恒瑞止盈 | 600276 ≥ 55 | info | 1/天 |

## 五、Cron 时段

```
9-11 点  每 5 分钟  (上午盘)
13-14 点 每 5 分钟  (下午盘)
15:05    收盘后 1 次
仅周一到周五
```

## 六、推送样式 (Mac 通知中心)

```
🟢 ADD: 消费50ETF - 跌穿0.95, 加7000股
价格 0.948 | 涨跌 -0.21% | 建议add 7000股
```

🔔 + 响铃 = 紧急 (日内-7% / 组合-3%)

## 七、数据落盘位置

```
data/
├── decisions.sqlite     交易决策 (主库)
├── screener.sqlite      扫描结果
├── monitor_state.json   监控触发历史 (7天)
├── monitor.log          监控运行日志 (cron)
├── notifier.log         推送历史
├── sentiment_state.json 情绪历史
├── macro_events.json    宏观事件库
└── goal_sim_history.json 目标概率历史
```

## 八、复盘节奏

```
每日 收盘后 15:30  monitor 自动跑 (捕捉收盘价)
每周日 晚上        跑 goal_sim + risk_metrics + sentiment
每月末 周日        跑 stats.py 看胜率/纪律
```

## 九、风控铁律

| 规则 | 阈值 |
|---|---|
| 单笔交易最大亏损 | 总资产 2% (1,576元) |
| 单一持仓最大占比 | 30% |
| 月度最大回撤 | -5% 触发减仓 |
| 强制减仓 | 9/30 仓位仍 >85% 减到 70% |

## 十、当前最重要的 3 个数字

```
持仓:    78,788
目标:    100,000
缺口:    21,212  ← 26.9% in 185 天
```

P(达成) 蒙特卡洛 5k 模拟 = 0.1% (纯被动持有)。
**必须主动加仓+择时** 才能达成。
