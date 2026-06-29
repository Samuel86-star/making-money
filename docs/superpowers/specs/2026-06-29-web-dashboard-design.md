# A股盯盘Web UI 设计文档

> 日期: 2026-06-29
> 状态: 设计已确认,待写实现计划
> Mockup: `.superpowers/brainstorm/49767-1782735150/content/c-design-v1.html`

## 一、目标与受众

**单一任务:** 盘中一眼抓机会点 + 持仓盈亏,不替下单(决策权在用户)。
**受众:** 单人CFO(本机盯盘)。
**非目标:** 不做下单、不做回测、不做选股策略编辑。只读看盘 + 机会挖掘展示。

## 二、技术栈

- **框架:** Streamlit(纯Python,与现有a_stock模块无缝集成,依赖仅加streamlit)
- **运行:** 本机 `streamlit run a_stock/web/dashboard.py`,浏览器开localhost
- **数据:** 实时算机会点(复用现有模块),不冲击数据源(东财push2限流)

## 三、设计系统(交易终端视觉)

避开AI默认三长相(cream+serif / 黑底酸绿 / broadsheet)。取材A股交易终端真实材料。

### 配色(5色,语义化)
| 色名 | Hex | 用途 |
|---|---|---|
| 深炭背景 | `#0a0e14` | 主背景(非纯黑,减眼疲劳) |
| 主文字白 | `#e8eaed` | 正文 |
| A股红 | `#f23645` | 涨(国内涨红跌绿,反国际) |
| A股绿 | `#089981` | 跌 |
| 琥珀黄 | `#d4a017` | 机会点/警示,唯一非涨跌色 |

### 字体(3角色)
- **显示/数据:** JetBrains Mono — 等宽,报价数字对齐(盯盘核心)
- **正文:** Inter — 中文友好
- (报价/盈亏/止损价全部等宽,对齐易读)

### 布局:C型(机会流 + 持仓侧栏)
```
┌─────────────────────────────────────────────┐
│  ▶ 行情滚动条 ticker tape (签名元素)         │
├─────────────────────────────────────────────┤
│ 总资产 │ 持仓市值 │ 现金 │ 浮盈 │ 距目标     │
├──────────────────────────────┬──────────────┤
│ 机会流 (时间倒序)             │ 持仓栏        │
│  📍09:50 159801 回踩买点      │ 600276 +7.75%│
│  ⚡09:48 002409 异动          │ 159801 +6.10%│
│  🎯09:35 000988 候选63分      │ 159915 +0.50%│
│  🔔待触 159516 规则≤1.85      │ 515650 +0.00%│
│                              │ 300059 -5.54%│
│                              ├──────────────┤
│                              │ 情绪30 谨慎   │
└──────────────────────────────┴──────────────┘
```

### 签名元素
顶部行情滚动条(ticker tape),横向滚动持仓+候选+观察池报价。券商终端灵魂,别处没有。`prefers-reduced-motion` 时停止动画。

### 机会流色条标记(4类)
| 类型 | 色条 | 标签色 | 触发源 |
|---|---|---|---|
| 📍 回踩买点 | 琥珀 | amber | 多头排列+回踩MA5/10不破(今天学的新能力) |
| ⚡ 异动 | 红 | red | anomaly.scan_holdings (火箭/跳水/资金surge) |
| 🎯 早盘候选 | 蓝 | blue | morning_scan top候选+评分 |
| 🔔 规则触发 | 绿 | green | rules.yaml命中 + watchlist回踩提醒 |

## 四、组件与数据流

### 组件(每个单一职责,可独立测)
1. `web/ticker.py` — 行情滚动条:拉持仓+候选+watchlist实时价,渲染marquee
2. `web/asset_bar.py` — 资产条:总资产/市值/现金/浮盈/距目标(读decisions.sqlite+risk_metrics)
3. `web/opportunity_feed.py` — 机会流:聚合4类机会,时间倒序,色条标记
4. `web/positions_panel.py` — 持仓栏:实时盈亏红绿+成本+ATR止损价(用risk_metrics._load_positions+ohlcv.struct_stop_loss)
5. `web/sentiment_bar.py` — 情绪条:sentiment温度+领涨板块

### 数据流
```
Streamlit (st.autorefresh 15s)
  → 各组件调 a_stock 现有模块
    → risk_metrics._load_positions() (持仓+成本+浮盈)
    → ohlcv.struct_stop_loss() (ATR止损价)
    → scorers/technical_scorer.score() (回踩买点识别)
    → anomaly.scan_holdings() (异动)
    → morning_scan 候选 (读scheduler.sqlite)
    → rules.yaml + watchlist (规则触发/观察池)
    → sentiment (情绪温度)
  → 渲染交易终端UI
```

### 机会点生成逻辑(实时算)
- **回踩买点:** 对持仓+watchlist,跑technical_scorer,检测多头排列+价回踩MA5/MA10(价在MA±1%内)且不破 → 标📍琥珀。这是今天学的铁律落地。
- **异动:** anomaly.scan_holdings()返回非空 → 标⚡红
- **候选:** 读scheduler.sqlite最近一次morning_scan的top5 → 标🎯蓝
- **规则:** rules.yaml命中(读monitor_log) + watchlist回踩提醒(159516≤1.85等)→ 标🔔绿

## 五、刷新策略

- `st.experimental_fragment` + `st.autorefresh(interval=15000)` — 15秒自动轮询
- 盘外(非9:30-15:00)降频到60秒,省请求
- 东财push2限流:复用`_common.py`的RateLimiter,UI层不再加压

## 六、文件结构

```
a_stock/web/
├── __init__.py
├── dashboard.py        # Streamlit入口 (st.set_page_config + 各组件拼装)
├── ticker.py           # 行情滚动条
├── asset_bar.py        # 资产条
├── opportunity_feed.py # 机会流(核心)
├── positions_panel.py  # 持仓栏
└── sentiment_bar.py    # 情绪条
```

入口: `streamlit run a_stock/web/dashboard.py`

## 七、错误处理

- 数据源失败(东财限流/网络):组件显示"行情暂不可用"占位,不崩整页
- DB读失败:持仓栏显示空状态"无持仓数据"
- parquet缺失(如159516):回踩买点该标的跳过,不影响其他

## 八、测试

- 各组件纯函数化(数据获取与渲染分离),单测数据聚合逻辑
- `opportunity_feed`: mock各模块返回,验证4类机会聚合+排序+色条标记
- `positions_panel`: mock _load_positions,验证成本/止损/盈亏渲染
- 不测Streamlit渲染本身(框架层)

## 九、不做(YAGNI)

- ❌ 下单/交易执行(决策权在用户,券商app操作)
- ❌ 历史回测
- ❌ 选股策略编辑
- ❌ 多用户/登录(单人本机)
- ❌ Docker部署(本机足够)
- ❌ WebSocket(轮询够用)

## 十、依赖变更

requirements.txt 仅加: `streamlit>=1.30`
