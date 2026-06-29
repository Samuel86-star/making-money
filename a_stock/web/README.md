# A股盯盘Web UI

交易终端式盯盘界面。机会流+持仓侧栏,实时算4类机会点。

## 启动

```bash
.venv/bin/streamlit run a_stock/web/dashboard.py
```

浏览器开 http://localhost:8501

## 功能

- **行情滚动条**: 持仓+观察池+候选报价横向滚动
- **资产条**: 总资产/市值/现金/浮盈/距目标
- **机会流** (4类):
  - 📍 回踩买点 (琥珀): 多头排列+回踩MA5/MA10不破
  - ⚡ 异动 (红): 火箭/跳水/资金surge
  - 🎯 早盘候选 (蓝): morning_scan top5
  - 🔔 规则 (绿): rules.yaml命中+watchlist提醒
- **持仓栏**: 实时盈亏红绿+真实成本+ATR止损
- **情绪条**: 市场温度+领涨板块

## 视觉

A股涨红跌绿(反国际)+琥珀机会色+JetBrains Mono等宽报价。
深炭背景减眼疲劳。不替下单,决策权在用户。

## 数据源

复用 a_stock 现有模块: risk_metrics / ohlcv / technical_scorer / anomaly / sentiment / morning_scan。
不冲击东财push2 (复用 _common 限流)。