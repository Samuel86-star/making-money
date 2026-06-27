# Project State — v1.0 完成 (2026-06-27)

## 角色 — 理财专家
不替下单, 推送后用户拍板。发现≠买, 每笔过 self_review 门禁。

## 目标
2026-12-31: 78,788 → 100,000 (+26.9%). v1.0 闭环 v0.5 P=0.1% → 30-40%.

## 持仓 (5+1)
515650(13k股 0.955) 600276(200 48.67) 300059(300 20.07) 159801(2k 1.547) 159915(2.7k 4.215)
股票42,644 + 现金36,144 = 总78,788. 候选: 515880(≤1.70 3k股)

## v1.0 6层 (2026-06-27完成)
发现: morning_scan / sector_rotation / strategies / anomaly
确认: deep_research / self_review / scorers(35/35/10/10/10)
执行: position_sizer / monitor / notifier(限流) / decision_log
调度: scheduler(多时间点+持久化+节假日) / close_scan
复盘: goal_sim / risk_metrics / sentiment(6阶段) / stats
辅助: macro_calendar / todo

集成6个GitHub: kimi(异动) a-share(限流) tickflow(策略) UZI(门禁+DCF) AI-agents(调度) KHunter(评分) quantdash(板块+情绪)
研究|架构|计划: docs/

## Cron v1.0 (5条已装)
monitor 9-11/13-14每5分 + 15:05(价格+异动) | scheduler 9-15每分(早盘9:35/9:50 + 盘后15:10)

## 关键节点
7/22政治局→8/15恒瑞中报→9/30再平衡→12/31 100k验收

## 排查
EPERM = TCC权限(开完全磁盘访问). 文件com.apple.provenance = 删旧文件重建
