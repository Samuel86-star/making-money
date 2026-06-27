# 参考项目研究笔记

> 2026-06-27. 谦卑学习 GitHub 6 个 A股机会发现开源项目。
> 目标: 集成精华进 `a_stock/`, 不重造轮子。

## 1. kimi_stock_advisor (异动监控+SQLite+飞书秒推)

### 异动信号算法 — 抄

**涨速** (`database.py:156-173`):
```python
now_time = df.iloc[-1]['timestamp']
target_time = now_time - pd.Timedelta(minutes=3)
idx_3min = df['timestamp'].searchsorted(target_time)  # 二分定位
speed_3min = ((price_now - price_3min) / price_3min) * 100
```

**量比关键洞见** (`database.py:181-197`):
```python
# EasyQuotation volume 是日内累计量! 必须先 diff
df_resampled = df.set_index('timestamp').resample('1min').last()
df_resampled['vol_delta'] = df_resampled['volume'].diff()  # 累计量→分钟增量
vol_ratio = latest_1min_vol / avg(past_30min_vol)
```

**触发** (`main.py:88-118`):
- 🚀 火箭发射: 涨速 > 1.0% 且 量比 > 1.5
- 🌊 高台跳水: 涨速 < -1.0%

### ⚠️ Bug 警告 — 平移必改

**跨午休涨速 bug**: `searchsorted(now-3min)` 不感知 11:30-13:00 空档。
下午开盘会算出 3.5 小时涨速。
**修复**: SQL 加 `WHERE time BETWEEN 09:25-11:30 OR 13:00-15:00`。

### SQLite schema — 抄
```sql
CREATE TABLE market_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME, code TEXT, price REAL,
    change_pct REAL, volume REAL
);
CREATE INDEX idx_code_timestamp ON market_snapshot (code, timestamp DESC);
```

## 2. a-share-quant-selector (钉钉推送工程化)

### RateLimiter 三闸门 — 必抄进 notifier.py

```python
class RateLimiter:
    def __init__(self, max_per_minute=20, min_interval=2.0):
        self.send_times = []
        self._lock_time = 0  # 限速错误后的锁定解除时刻

    def acquire(self):
        # 闸0: 限速锁定 (状态化罚时)
        # 闸1: 每分钟配额 (20)
        # 闸2: 最小间隔 (2s)

    def on_rate_limit_error(self, retry_count):
        backoff = min(2 ** retry_count, 30)  # 上限30s
        self._lock_time = time.time() + backoff
```

**关键**: `_lock_time` 状态化罚时 — 一次限速错误阻塞后续所有发送, 比单条重试更稳。

### 重试 — 抄

```python
for attempt in range(max_retries + 1):  # 4次尝试
    self._rate_limiter.acquire()
    response = requests.post(...)
    if errcode == 660026:  # 钉钉限速专属
        self._rate_limiter.on_rate_limit_error(attempt)
    elif HTTP error:
        time.sleep(2 ** attempt)  # 1,2,4,8s
```

**区分**: 业务错误(非限速)直接 return False 不重试, 避免无效重试。

### 大消息分段 — 抄

>18KB 按行切, 超长行 UTF-8 安全 chunk (逐步回退 1-4 字节找完整字符边界)。

## 3. tickflow-stock-panel (发现器, 388 star)

### 策略=信号列组合 — 抄架构

新增策略零成本, 只组合已有 `signal_*` 列:
```python
# builtin/trend_breakout.py
META = {"id":..., "name":..., "params":[...], "scoring":{col:weight}}
ENTRY_SIGNALS = [...]
def filter(df, params) -> pl.Expr:  # 返回布尔 Polars 表达式
```

### 三阶段引擎 — 抄

`engine.py:187 run()`: basic_filter → filter_fn → min-max 评分 (0-100)

### 动态涨停价 — 必抄 (A股特色)

```python
# builtin/near_limit_up.py
is_st = pl.col("name").str.contains("(?i)ST")
is_cyb = pl.col("symbol").str.starts_with("300") | starts_with("301")
return pl.when(is_st).then(0.05).when(is_cyb|kcb).then(0.20)
         .when(bj).then(0.30).otherwise(0.10)
```

### Polars 向量化 — 思路抄

```python
pl.col("close").rolling_mean(5).over("symbol").alias("ma5")
pl.col("close").rolling_max(60).over("symbol").alias("high_60d")
```
零 Python 循环。当前我用 pandas, 暂不换, 但新扫描器用 Polars。

### 诚实声明
- "20 策略" 实测 18 个, README 营销取整
- 无 benchmark 数字, 只有架构证据
- 单 connection + 锁, 高并发会串行化

## 4. UZI-Skill (深研器, 4614 star)

### self-review 物理门禁 — 必抄

```python
# assemble_report.py
review = review_all(ticker)
if review["critical_count"] > 0:
    raise RuntimeError(f"⛔ BLOCKED: {crit} 个 critical 问题")
# critical>0 时 HTML 物理写不出
```

每条 issue 带 `suggested_fix`, agent 可自愈重跑。

### BUG→check→测试 闭环 — 必抄

每踩一个坑沉淀成 check 函数 + 回归测试。比 prompt 技巧管用。

### 22 维加权打分

最高权重: 财务5 / 估值5 / **杀猪盘检测5** (A股特色)
`overall = fund_score*0.6 + consensus*0.4`

### 66 评委 × 242 规则

```python
@dataclass
class Rule:
    rule_id: str; name: str; weight: int  # 1-5
    check: Callable[[dict], bool]  # 布尔, 不是分数
    pass_msg: str; fail_msg: str
```

### 17 机构方法 — 选 6 个深研用

DCF + Comps + beat/miss + 催化剂 + DD清单 + Segmental

### 诚实声明
- "板块轮动/北向/融资融券 skill" **不存在**, README 营销夸张
- "13 条 check" 实测 16 个
- "80/65/50/35 四档" 实际 8 档

## 5. aiagents-stock (1570 star, 水分大)

### 4 个预设错误 (诚实纠正)

1. "新浪扫5000只" = 误传, 实际全市场排名靠问财服务端 (pywencai)
2. "三套AI并行" = 假并行, 串行+sleep(1)
3. "板块4-agent按强势/潜力/衰退" = 按维度分工, 标签全LLM, 不可回测
4. "龙虎榜5位并列" = 4+1结构, 第5位汇总者

### 值得抄 (10项)

1. `get_trading_session` 6段交易时段 (集合竞价/午休/尾盘) — `smart_monitor_deepseek.py:61-140`
2. 多时间点注册+热重载 — `portfolio_scheduler.py:551-554`
3. 每只独立 next_check 扫描循环 — `monitor_service.py:77-110`
4. 非阻塞锁防重入 `acquire(blocking=False)` — `sector_strategy_scheduler.py:98-108`
5. SQL时间窗去重 + pending/sent队列 — `monitor_db.py:186-282`
6. **5维度分段量化评分 (唯一可回测!)** — `longhubang_scoring.py:39-76`
7. pywencai 多方案降级查询 — `main_force_selector.py:49-103`
8. JSON解析三层兜底+本地降级 — `main_force_analysis.py:483-537`
9. 4+1多分析师编排 (抄结构改真并行) — `longhubang_engine.py:117-150`
10. 数据截断+摘要喂AI (token控制) — `longhubang_data.py:241-306`

### 必须避开的坑 (10项)

- 假并行 / LLM异常污染结论 / 通知无限流被封
- LLM-as-judge不可回测 / schedule.clear()误杀
- JSON键名不对齐推荐永远空 / 无WAL locked风险
- 钉钉加签缺失 / 任务不持久化 / 节假日未实现

### 关键认知

> 我的 monitor.py (腾讯批量) + screener.py (东财push2) **比参考项目强**。
> 该抄: 评分模型 + 调度编排 + 去重队列。不抄数据层。

## 6. KHunter (多因子评分, 278 star)

### 权重 35/35/10/10/10 — 属实但有缺陷

```python
SCORE_WEIGHTS = {"technical":0.35, "moneyflow":0.35, "fundamental":0.10, "sector":0.10, "event":0.10}
VETO_SCORE = -100
```

### ⚠️ 重大缺陷 (抄时必改)

1. **各因子 native range 不一致 + 未归一化**
   - 技术面无界 (命中4个正策略=200×0.35=70直达"推荐")
   - 资金面 ~[-51,+110]
   - 基本面 [-10,+110]→clamp
   - **改进**: 每因子先 clamp [0,100] 再加权
2. **2个veto死代码**: 基本面/板块 veto 永不触发
3. **文档漂移**: docstring 与常量多处不符 (moneyflow内部权重/veto阈值/sector"近5日")

### 抄什么
- 权重常量结构 (SCORE_WEIGHTS dict)
- 一票否决机制 (veto→-100短路)
- 分档评分函数形态 (moneyflow _score_main_net_flow 分档step)
- **只抄技术/资金/事件三类真veto**

### 不抄什么
- 不归一化设计
- 死代码 veto
- BaseStrategy + 16策略体系 (太重, 跟我 candidate_filter 冲突)
- 技术面读"策略命中表" (耦合过重, 我直接算MA/MACD/RSI)

## 7. quantdash (工作流+板块轮动, 87 star)

### 板块持续性算法 — 最干净可平移

`fetch_sector_snapshots.py:131-199` 200行纯Python, 四指标:
```python
streakDays            # 同板块连续领涨天数
topThreeAppearances   # 5日内进top3次数
strengthDelta         # 涨势加速 (leader.pctChange - prev)
strongestRepeatName   # 真主线 (5日top3出现最多)
```
判断: streakDays高 + topThreeAppearances高 + strengthDelta正 = 持续主线

### 局限 (我可加强)
只看 pctChange 排名, **无资金流/成交额**。我 `sectors.py` 能拉资金流 → 加 capital_concentration 字段双重确认。

### 情绪周期 6阶段 (超短视角)
退潮/冰点/修复/主升/试错/分歧
- 修复率 = 昨日炸板池票次日收盘涨
- 高位风险: A杀≤-8 / broken_rate≥35→high

### MCP Server — 12工具 (非13)
抄: list-then-read组合 + readAdvice meta + 严格只读
修: 切片重建全dashboard(加缓存) / handler不catch / 无分页

### 不抄什么
- LLM盘前计划 (我无LLM集成, 投入大)
- watcher循环 (我用cron更标准)
- 7个JSON文件拆分 (我用SQLite一张表)

## 8. 集成决策汇总 (6项目全部研究完)

### 必抄 (高优先, 周一前)
| 模块 | 抄自 | 抄什么 |
|---|---|---|
| notifier.py增强 | a-share | RateLimiter三闸门 + 重试 |
| 新anomaly.py | kimi | 火箭发射/高台跳水 (修午休bug) |
| position_sizer增强 | KHunter | 多因子35/35/10/10/10 (改归一化) |

### 该抄 (中优先, 1-2周)
| 模块 | 抄自 | 抄什么 |
|---|---|---|
| 新morning_scan.py | aiagents-stock | pywencai多方案降级 + 5维评分 |
| 新sector_rotation.py | quantdash | 四指标持续性算法 (加资金流) |
| 新strategies/ | tickflow | 策略=信号列组合 + 动态涨停价 |
| 新scheduler.py | aiagents-stock | 多时间点+热重载+持久化(补WAL) |

### 慎抄 (低优先, 思路为主)
| 模块 | 抄自 | 抄什么 |
|---|---|---|
| 新deep_research.py | UZI | DCF+Comps+DD清单 (17法选6) |
| 新self_review.py | UZI | 物理门禁 + BUG→check→测试 |
| sentiment增强 | quantdash | 6阶段情绪周期 |

### 绝不抄 (避坑)
- aiagents-stock 假并行 / LLM污染结论 / 通知无限流
- KHunter 不归一化 / 死veto / 16策略体系
- quantdash LLM盘前计划 / watcher循环 / JSON双源
- tickflow Polars全换 (我pandas够用) / DTW形态 (周期不匹配)

## 集成计划 (草稿, 等全部研究完定稿)

### 必抄 (高优先)
1. `notifier.py` 加 RateLimiter + 重试 (抄 a-share)
2. 新 `anomaly.py` 异动信号 (抄 kimi, 修午休 bug)
3. `position_sizer.py` 加多因子评分 (抄 KHunter 权重)

### 该抄 (中优先)
4. 新 `morning_scan.py` 全市场扫描 (抄 aiagents-stock 架构)
5. 新 `sector_rotation.py` 板块轮动 (抄 quantdash)
6. `candidate_history` 表加字段 (异动类型/评分)

### 慎抄 (低优先, 思路为主)
7. Polars 向量化 (tickflow) — 当前 pandas 够用
8. DTW 形态匹配 (a-share) — 周期不匹配, 需重定义
9. 22 维深研 (UZI) — 太重, 选 5-8 维即可
