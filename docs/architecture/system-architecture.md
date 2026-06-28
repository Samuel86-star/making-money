# A股决策系统架构 (v1.0)

> 2026-06-27 · 发现→确认→执行→复盘 闭环
> 78,788 → 100,000 (+26.9% in 187d), P(达成) 0.2%

## 分层架构

```mermaid
graph TB
    subgraph 数据源["🌐 数据源层 a_stock_data/"]
        EM[东财 eastmoney<br/>资金流/板块/龙虎榜/研报]
        TX[腾讯 tencent<br/>实时报价 qt.gtimg.cn]
        THS[同花顺 ths<br/>热度/EPS/北向]
        FN[新浪 financials<br/>三表/公告 filings]
        SC[板块排行 sectors]
        OH[ohlcv<br/>K线/技术指标]
    end
    end

    subgraph 发现["🔍 发现层 (策略+早盘+异动)"]
        STR[strategies/<br/>5策略 Signal Bridge<br/>→ 信号聚合 → topM]
        MS[morning_scan<br/>9:35/9:50 策略候选+5维评分<br/>→ 信号桥接 → top5推送]
        AN[anomaly<br/>火箭发射/高台跳水<br/>3min涨速+量比]
        SR[sector_rotation<br/>板块轮动持续性<br/>4指标 + 资金流加强]
    end

    subgraph 评分["📊 评分层 scorers/"]
        TOT[total_scorer<br/>综合评分 + 否决]
        TC[technical<br/>技术面 35%]
        MF[moneyflow<br/>资金面 35%]
        FD[fundamental<br/>基本面 10%]
        SS[sector<br/>板块 10%]
        EV[event<br/>事件 10%]
    end

    subgraph 确认["✅ 确认层"]
        DR[deep_research<br/>DCF+Comps+DD清单]
        SRV[self_review<br/>门禁 critical>0→阻断]
        BRF[生产者简报 brief]
    end

    subgraph 调度["⏰ 调度层"]
        SCH[scheduler<br/>多时间点+6段时段+节假日]
        CR[cron<br/>交易时段每5min触发]
    end

    subgraph 执行["⚡ 执行层"]
        MON[monitor<br/>11条规则+异动+非阻塞锁]
        RUL[rules.yaml<br/>规则配置]
        NOT[notifier<br/>osascript + RateLimiter三闸门]
        PS[position_sizer<br/>凯利公式]
        DL[a_screen/decision_log<br/>决策DB读写]
    end

    subgraph 复盘["📊 复盘层"]
        CS[close_scan<br/>15:10盘后落盘]
        SEN[sentiment<br/>北向+龙虎榜+研报热度 0-100]
        GS[goal_sim<br/>蒙特卡洛 P(达成)]
        RM[risk_metrics<br/>Sharpe/MaxDD/波动率]
        STA[stats<br/>胜率/纪律分析]
    end

    subgraph 辅助["🛠 辅助"]
        MC[macro_calendar<br/>宏观事件]
        TD[todo<br/>待办系统]
        LOG[log.py<br/>CLI写入DB]
    end

    subgraph 存储["💾 存储 data/"]
        DB1[(decisions.sqlite)]
        DB2[(screener.sqlite<br/>+daily_close)]
        DB3[(scheduler.sqlite WAL)]
        DB4[(anomaly_ticks.sqlite)]
        DB5[(sector_rotation.sqlite)]
        ST1[monitor_state.json]
        ST2[sentiment_state.json]
        ST3[self_review_issues.json]
    end

    %% 数据源 → 发现
    EM --> MS
    TX --> AN
    SC --> SR
    EM --> SR

    %% 策略层内部 (Signal Bridge)
    STR -.->|topM 候选| MS
    STR --> OH
    STR --> EM

    %% 发现层内部
    MS -.-> SR
    MS --> TOT
    TOT --> TC
    TOT --> MF
    TOT --> FD
    TOT --> SS
    TOT --> EV

    %% 发现/评分 → 确认
    MS -.-> DR
    DR --> SRV
    SRV -->|critical=0| BRF

    %% 确认 → 执行
    BRF --> PS
    PS --> DL
    DL --> DB1

    %% 调度 → 发现/执行
    CR --> SCH
    SCH --> MS
    SCH --> AN
    SCH --> CS
    SCH --> MON

    %% 执行层内部
    MON --> RUL
    MON --> AN
    MON --> TX
    MON --> NOT
    MON --> ST1
    MON --> DB1

    %% 复盘
    CS --> DB2
    DL --> CS
    DL --> SEN
    DB2 --> SEN
    DL --> GS
    DL --> RM
    DL --> STA

    %% 辅助
    LOG --> DL
    MC -.-> MON
    TD -.-> LOG

    %% 推送 → 用户
    NOT -.推送.-> USER[👨 用户<br/>看弹窗→券商app下单]
    MS -.推送.-> USER

    style MS fill:#e1f5ff,stroke:#06c
    style AN fill:#e1f5ff,stroke:#06c
    style SR fill:#e1f5ff,stroke:#06c
    style DR fill:#fff5e1,stroke:#c80
    style SRV fill:#fff5e1,stroke:#c80
    style MON fill:#ffe,stroke:#c90
    style NOT fill:#ffe,stroke:#c90
    style USER fill:#e1f5e1,stroke:#3c3
```

## 策略层内部架构 (Signal Bridge)

```mermaid
graph TB
    subgraph 策略容器["strategies/"]
        BASE[base.py<br/>StrategyMeta + BaseStrategy<br/>META/filter/signals 三段式]

        REG[registry.py<br/>importlib 目录反射<br/>自动注册]

        SGN[signals.py<br/>Signal{code,action,<br/>confidence,strategy,reason}]

        RUN[runner.py<br/>build_indicators<br/>→ run_all → SignalVote]

        NL[near_limit_up<br/>逼近涨停<br/>涨>7%+距涨停<3%]
        TB[trend_breakout<br/>趋势突破<br/>close>ma60+新高+量比≥2]
        OB[oversold_bounce<br/>超跌反弹<br/>RSI<30+收阳+量比≥1.2]
        MF[moneyflow_surge<br/>资金流异动<br/>东财净流入排名]
        SM[sector_momentum<br/>板块动量<br/>轮动领头羊]
    end

    subgraph 数据输入["数据源"]
        OH[ohlcv/ K线 + 技术指标]
        EM[东财 资金流/板块]
        TX[腾讯 实时价]
    end

    subgraph 输出["输出到 morning_scan"]
        WL[watchlist<br/>SignalVote 聚合 topM]
    end

    OH --> RUN
    EM --> RUN
    TX --> RUN

    REG --> RUN
    BASE --> NL
    BASE --> TB
    BASE --> OB
    BASE --> MF
    BASE --> SM

    RUN --> SGN
    SGN -->|SignalVote| WL

    NL -.-> RUN
    TB -.-> RUN
    OB -.-> RUN
    MF -.-> RUN
    SM -.-> RUN

    style NL fill:#0d4194,stroke:#58a6ff
    style TB fill:#0d4194,stroke:#58a6ff
    style OB fill:#0d4194,stroke:#58a6ff
    style MF fill:#0d4194,stroke:#58a6ff
    style SM fill:#0d4194,stroke:#58a6ff
```

### Signal 数据流 in morning_scan

```mermaid
sequenceDiagram
    participant MS as morning_scan
    participant RUN as runner
    participant S1 as trend_breakout
    participant S2 as oversold_bounce
    participant S3 as near_limit_up
    participant S4 as moneyflow_surge
    participant S5 as sector_momentum
    participant VOTE as SignalVote
    participant SCORE as scorers 5维
    participant W as watchlist

    MS->>RUN: 全市场 topN 代码列表
    RUN->>RUN: build_indicators(code) → 共享指标

    par 每个策略
        RUN->>S1: filter(code, indicators)
        S1-->>RUN: eligible?
        RUN->>S1: signals(code, indicators)
        S1-->>RUN: Signal[]
    and
        RUN->>S2: filter + signals
        S2-->>RUN: Signal[]
    and
        RUN->>S3: filter + signals
        S3-->>RUN: Signal[]
    and
        RUN->>S4: filter + signals
        S4-->>RUN: Signal[]
    and
        RUN->>S5: filter + signals
        S5-->>RUN: Signal[]
    end

    RUN->>VOTE: 聚合所有 Signal
    VOTE->>VOTE: 按 code 聚合同票 + 加权 confidence
    VOTE-->>MS: topM 候选 (按 confidence 排序)

    MS->>SCORE: 对 topM 做 5 维评分
    SCORE-->>MS: 总分 + 否决
    MS->>W: 写入 watchlist top5
```

## 核心数据流 (发现→确认→执行→复盘)

```mermaid
sequenceDiagram
    participant C as cron
    participant SCH as scheduler
    participant MS as morning_scan
    participant RUN as strategies/runner
    participant VOTE as SignalVote
    participant SCORE as 5维评分
    participant SR as sector_rotation
    participant W as watchlist
    participant DR as deep_research
    participant SRV as self_review
    participant U as 👨用户
    participant R as rules.yaml
    participant M as monitor
    participant N as notifier
    participant CL as close_scan
    participant SEN as sentiment

    %% 早盘
    C->>SCH: 每1min检查到点任务
    SCH->>MS: 09:35 早盘扫描
    MS->>RUN: 全市场topN → 策略信号
    RUN->>RUN: 5策略并行 filter+signals
    RUN->>VOTE: 聚合 Signal
    VOTE-->>MS: topM 候选 (按 confidence)
    MS->>SCORE: topM → 5维评分
    SCORE-->>MS: 总分 + 否决
    MS->>SR: 板块轮动
    SR-->>MS: 领涨板块/主线
    MS->>W: top5 写 watchlist
    MS->>N: 推送候选
    N->>U: Mac弹窗 "早盘候选top5"

    %% 确认 (用户主动)
    U->>DR: 开会话喊深研
    DR->>DR: DCF+Comps+DD
    DR->>SRV: self-review门禁
    alt critical>0
        SRV--xDR: ⛔ 阻断
    else critical=0
        SRV->>U: 报告+仓位建议
        U->>R: 同意→设买点进rules
    end

    %% 交易时段
    C->>SCH: 每5min触发交易时段
    SCH->>M: 监控循环
    M->>M: 拉实时价+比对11条规则
    M->>M: 异动检测 (火箭/跳水)
    alt 命中规则 or 异动
        M->>N: 推送(title, body)
        N->>U: Mac弹窗 → 用户下单
    end

    %% 盘后
    C->>SCH: 15:10
    SCH->>CL: 盘后落盘
    CL->>CL: 板块snapshot+情绪+持仓评分
    CL->>SEN: 北向/龙虎榜/研报热度
    CL->>N: 推送 "盘后摘要"
    N->>U: Mac弹窗
```

## 模块依赖关系

```mermaid
graph LR
    subgraph 外部依赖
        AP[qt.gtimg.cn 实时价]
        EP[东财push2 资金流/板块]
        TP[腾讯行情]
        SP[新浪财报]
        HP[同花顺热度]
    end

    subgraph 内部依赖
        CFG[config.py<br/>路径/权重/限流]
        DB[db.py<br/>schema+helpers]
        OH[ohlcv.py<br/>K线加载]
        CM[_common.py<br/>限流/缓存/重试]
    end

    AP --> monitor
    AP --> anomaly
    AP --> strategies
    EP --> morning_scan
    EP --> sector_rotation
    EP --> sentiment
    EP --> strategies
    TP --> monitor
    TP --> eastmoney
    SP --> financials
    HP --> ths

    CFG --> 所有模块
    DB --> log
    DB --> close_scan
    DB --> goal_sim
    DB --> risk_metrics
    OH --> deep_research
    OH --> strategies
    CM --> eastmoney
    CM --> tencent
```

## 评分权重

```mermaid
pie title 多因子评分权重 (总分100)
    "技术面 technical" : 35
    "资金面 moneyflow" : 35
    "基本面 fundamental" : 10
    "板块 sector" : 10
    "事件 event" : 10
```

## 监控规则分类

```mermaid
graph LR
    subgraph 加仓["加仓 (add) 5条"]
        A1[消费ETF 阶梯1 ≤0.95]
        A2[消费ETF 阶梯2 ≤0.93]
        A3[恒瑞 回踩47-48]
        A4[通信ETF ≤1.70]
        A5[通信ETF 加码 ≤1.60]
    end

    subgraph 风控["风控 (info) 2条"]
        R1[单标的日内-7%]
        R2[组合日内-3%]
    end

    subgraph 止盈["止盈 (reduce/info) 2条"]
        P1[创业板ETF ≤4.00]
        P2[恒瑞 ≥55.0]
    end

    A1 --> MON[monitor 每5min<br/>比对 + 异动]
    A2 --> MON
    A3 --> MON
    A4 --> MON
    A5 --> MON
    R1 --> MON
    R2 --> MON
    P1 --> MON
    P2 --> MON

    MON -->|命中| NOT[notifier<br/>RateLimiter三闸门]
    NOT -->|弹窗| USER[👨 用户下单]
```

## 异动检测流程

```mermaid
sequenceDiagram
    participant M as monitor
    participant A as anomaly
    participant GT as qt.gtimg.cn
    participant TK as anomaly_ticks.sqlite
    participant N as notifier
    participant U as 👨用户

    M->>A: 每5min调用 (持仓+候选)
    A->>GT: 拉实时价+量比
    GT-->>A: 价/量/涨速
    A->>TK: 写 tick 缓存 (保留3天)
    A->>A: 算3min涨速 + 量比
    alt 涨速>1% 且 量比>1.5
        A->>N: 🚀 火箭发射
    else 涨速<-1%
        A->>N: 🌊 高台跳水
    end
    N->>U: Mac弹窗
```

## 存储结构

```mermaid
graph TB
    subgraph SQLite["SQLite 数据库 (5)"]
        D1[decisions.sqlite<br/>决策日志/持仓/资金曲线]
        D2[screener.sqlite<br/>全市场扫描/daily_close]
        D3[scheduler.sqlite<br/>WAL 调度持久化]
        D4[anomaly_ticks.sqlite<br/>tick 缓存 3天]
        D5[sector_rotation.sqlite<br/>板块轮动历史]
    end

    subgraph JSON["JSON 状态 (4)"]
        J1[monitor_state.json<br/>规则触发历史]
        J2[sentiment_state.json<br/>情绪序列]
        J3[self_review_issues.json<br/>门禁issue记录]
        J4[todo.json<br/>待办]
    end

    subgraph 其他[其他]
        O1[ohlcv/ K线目录]
        O2[screen/daily/ 日扫描]
        O3[a_share_list.json<br/>全市场列表]
    end
```

## 缺口 & 待改进

| # | 缺口 | 影响 | 优先级 |
|---|------|------|--------|
| 1 | 无 parquet 存 enriched 全市场 | 情绪/回测需重拉, 计算冗余 | 低 |
| 2 | 无多券商对接 | 仅弹窗, 不能自动下单 (设计如此) | — |

## 技术债 & 约束

- **Python 3.12+** · **SQLite (5 库)** · **无外部消息队列**
- 所有模块通过 `config.py` 共享路径/权重
- `scheduler.py` 是唯一入口调度器 (取代裸 cron)
- 通知限流三闸门: 20条/min + 0.5s间隔 + 错误锁定
- 非阻塞锁防重入: morning_scan, monitor, anomaly 均有 threading.Lock
