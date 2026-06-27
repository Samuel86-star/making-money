# strategies/ 策略模块设计 (Signal Bridge)

> 2026-06-27 · 发现层策略矩阵, 接入 morning_scan
> 状态: 设计已确认, 待实现

## 目标

为发现层增加多策略信号矩阵. 策略快速发现候选 → SignalVote 聚合 → morning_scan 接 scorers 5维评分深度确认 → watchlist. 策略与评分不重叠: 策略=发现, 评分=确认.

## 背景

- `strategies/` 目录原有源码已删, 仅留 pyc 残留. pyc 反编译确认旧架构: base/registry/runner + 3策略
- ohlcv 数据已就绪: 全市场 5206 只 parquet, 大部分 244 根K线 (1年), 远超 ma60 需求. 列名 `Open/High/Low/Close/Volume` (首字母大写)
- GitHub 参考: tickflow(骨架三段式), KHunter(registry反射), CopilotQuant(Signal quality), Alpacalyzer(protocol), Qlib(太重跳过)

## 模块结构

```
a_stock/strategies/
├── __init__.py          # 导出 Signal, run_all, list_strategies
├── base.py              # StrategyMeta + BaseStrategy (三段式)
├── signals.py           # Signal dataclass + SignalVote 聚合
├── registry.py          # importlib 目录反射自动注册
├── runner.py            # build_indicators + run_all
├── near_limit_up.py     # 逼近涨停 涨>7%+距涨停<3% (0.6)
├── trend_breakout.py    # 趋势突破 close>ma60+60日新高+量比≥2 (0.7)
├── oversold_bounce.py   # 超跌反弹 RSI<30+收阳+量比≥1.2 (0.5)
├── moneyflow_surge.py   # 资金流异动 候选池内净流入前列 (0.6)
└── sector_momentum.py   # 板块动量 主线板块成分股 (0.5)
```

依赖方向 (单向无环):
```
runner → registry → 各策略 → base
runner → signals
各策略 → base, signals, ohlcv/eastmoney/sector_rotation (数据)
```

## 核心数据结构

### Signal (signals.py)

```python
@dataclass
class Signal:
    code: str              # 6位代码
    name: str              # 标的名称
    action: str            # "buy" / "sell" / "hold"
    confidence: float      # 0.0 ~ 1.0
    strategy: str          # 来源策略名
    reason: str            # 一句话理由 (推送用)
    meta: dict = None      # 额外数据
```

### SignalVote 聚合

```python
@dataclass
class SignalVote:
    code: str
    name: str
    total_confidence: float   # 所有 buy 信号 confidence 之和
    strategies: list[str]     # 投票策略名列表
    signals: list[Signal]     # 原始信号明细
    top_reason: str           # confidence 最高那条 reason

def aggregate(signals: list[Signal]) -> list[SignalVote]:
    """按 code 聚合同票, 只保留 action=buy, 按 total_confidence 降序."""
```

### BaseStrategy 三段式 (base.py)

```python
@dataclass
class StrategyMeta:
    name: str
    confidence: float
    description: str

class BaseStrategy(ABC):
    META: StrategyMeta  # 子类必须声明

    @abstractmethod
    def filter(self, code: str, name: str) -> bool:
        """初筛: 标的适不适合本策略"""

    @abstractmethod
    def signals(self, code: str, name: str) -> list[Signal]:
        """产信号: 满足条件返回 Signal[], 否则空列表"""

    def evaluate(self, code: str, name: str) -> list[Signal]:
        """模板方法: filter 通过才跑 signals, 异常兜底返回 []"""
        if not self.filter(code, name):
            return []
        try:
            return self.signals(code, name) or []
        except Exception:
            return []

def limit_pct(code: str) -> float:
    """涨停幅度: 60/68开头 20%, 创业板/科创板 20%, 主板 10%"""
```

## confidence 阈值表 (方案 A 固定阈值)

| 策略 | confidence | 理由 |
|------|-----------|------|
| trend_breakout | 0.7 | 突破信号较强 |
| near_limit_up | 0.6 | 强势但追高风险 |
| moneyflow_surge | 0.6 | 资金驱动 |
| sector_momentum | 0.5 | 板块跟随, 个股需再筛 |
| oversold_bounce | 0.5 | 抄底信号偏弱 |

多策略同票叠加: trend_breakout(0.7) + moneyflow_surge(0.6) 同命中 → total_confidence=1.3, 排序靠前.

## registry.py (自动注册)

```python
import importlib, pkgutil
from a_stock.strategies.base import BaseStrategy

_REGISTRY: dict[str, BaseStrategy] = {}

def _scan() -> None:
    """目录反射: 扫描 strategies/ 下所有非下划线非骨架模块, 收集 BaseStrategy 子类实例."""
    import a_stock.strategies as pkg
    for _, modname, _ in pkgutil.iter_modules(pkg.__path__):
        if modname.startswith("_") or modname in ("base", "registry", "runner", "signals"):
            continue
        mod = importlib.import_module(f"a_stock.strategies.{modname}")
        for attr in vars(mod).values():
            if (isinstance(attr, type) and issubclass(attr, BaseStrategy)
                    and attr is not BaseStrategy and attr.__module__ == mod.__name__):
                inst = attr()
                _REGISTRY[inst.META.name] = inst

def get_all() -> list[BaseStrategy]:
    if not _REGISTRY: _scan()
    return list(_REGISTRY.values())

def get(name: str) -> BaseStrategy | None:
    if not _REGISTRY: _scan()
    return _REGISTRY.get(name)

def list_strategies() -> list[str]:
    if not _REGISTRY: _scan()
    return list(_REGISTRY.keys())
```

新增策略零成本: 丢个 `xxx.py` 进目录, 定义 `class Xxx(BaseStrategy)`, 自动注册, 不改 registry.

## runner.py (编排)

```python
def build_indicators(code: str) -> dict | None:
    """读 ohlcv parquet, 算共享指标. 数据不足返回 None.
    返回 {df, ma60, rsi, high_60d, vol_ratio, last_close, change_pct}."""

def run_all(candidates: list[dict]) -> list[SignalVote]:
    """对候选池跑所有策略, 聚合 SignalVote.
    1. 遍历 candidates
    2. 每 code 调 build_indicators (一次, 共享)
    3. 每策略调 evaluate(code, name) → Signal[]
    4. 全部 Signal → aggregate() → SignalVote[]
    5. 按 total_confidence 降序返回"""

def run_top(candidates: list[dict], top_m: int = 20) -> list[SignalVote]:
    """run_all 后取 topM."""
```

关键设计:
- `build_indicators` 每票只算一次, 5策略共享, 避免重复读 parquet
- 候选池 50 × 5策略 = 250 次 evaluate
- 单策略异常在 `BaseStrategy.evaluate` 兜底
- `build_indicators` 返回 None 跳过该 code

### 共享指标 build_indicators 输出

```python
{
    "df": DataFrame,
    "ma60": float,          # 60日均线
    "rsi": float,           # 14日RSI
    "high_60d": float,      # 60日最高价
    "vol_ratio": float,     # 量比 (今量/5日均量)
    "last_close": float,
    "change_pct": float,    # 日内涨幅 (Close/Open-1)
}
```

## 5个策略逻辑

### trend_breakout.py (0.7)

```python
class TrendBreakout(BaseStrategy):
    META = StrategyMeta("trend_breakout", 0.7, "趋势突破")

    def filter(self, code, name):
        ind = build_indicators(code)
        return ind is not None and len(ind["df"]) >= 60

    def signals(self, code, name):
        ind = build_indicators(code)
        df = ind["df"]
        last = df.iloc[-1]
        cond = (
            last["Close"] > ind["ma60"]
            and last["Close"] >= ind["high_60d"]
            and ind["vol_ratio"] >= 2.0
        )
        if cond:
            return [Signal(code, name, "buy", 0.7, "trend_breakout",
                          f"突破60日新高{ind['high_60d']:.2f} 量比{ind['vol_ratio']:.1f}",
                          {"price": float(last["Close"]), "ma60": ind["ma60"]})]
        return []
```

### oversold_bounce.py (0.5)

```python
def signals(self, code, name):
    ind = build_indicators(code)
    df = ind["df"]
    last, prev = df.iloc[-1], df.iloc[-2]
    cond = (
        ind["rsi"] < 30
        and last["Close"] > last["Open"]
        and ind["vol_ratio"] >= 1.2
    )
```

### near_limit_up.py (0.6)

```python
def signals(self, code, name):
    ind = build_indicators(code)
    last = ind["df"].iloc[-1]
    change_pct = (last["Close"] - last["Open"]) / last["Open"] * 100
    limit = limit_pct(code)
    dist_to_limit = limit - change_pct
    cond = change_pct > 7 and 0 < dist_to_limit < 3
```

### moneyflow_surge.py (0.6)

```python
class MoneyflowSurge(BaseStrategy):
    META = StrategyMeta("moneyflow_surge", 0.6, "资金流异动")
    _rank: dict = {}  # runner 在 run_all 前注入 {code: rank}

    def signals(self, code, name):
        # 候选池已按资金流排序, 前10名触发
        rank = self._rank.get(code, 999)
        ind = build_indicators(code)
        if rank <= 10 and ind["df"].iloc[-1]["Close"] > ind["df"].iloc[-2]["Close"]:
            return [Signal(..., 0.6, "moneyflow_surge", f"资金流排名#{rank}")]
```

runner 在 `run_all` 开始时, 按 candidates 顺序 (screener 已按净流入排序) 构建 `{code: 1-based_rank}`, 注入到 `MoneyflowSurge._rank` 和 `SectorMomentum._main_sector_stocks`.

### sector_momentum.py (0.5)

```python
def signals(self, code, name):
    from a_stock.sector_rotation import analyze
    sr = analyze()
    if not sr or code not in self._main_sector_stocks:
        return []
    ind = build_indicators(code)
    if ind["change_pct"] > 3:
        return [Signal(..., 0.5, "sector_momentum",
                      f"主线板块{sr.strongest_repeat_name}成分 涨{ind['change_pct']:.1f}%")]
```

注意: moneyflow_surge 和 sector_momentum 需候选池上下文 (排名/成分股), runner 注入, 不在 build_indicators.

## morning_scan 接入 (方案1 策略前置过滤)

`morning_scan._scan_impl` 最小侵入改动:

```python
stocks = fetch_market_stocks(top_n=top_n)  # 资金流 top50

# 新增: 策略层先跑
from a_stock.strategies.runner import run_top
try:
    votes = run_top(stocks, top_m=20)
    strategy_codes = {v.code for v in votes}
    scored_codes = strategy_codes | {s["code"] for s in stocks[:10]}
except Exception:
    scored_codes = {s["code"] for s in stocks[:top_n]}  # 回退纯 screener

# 后续 score_candidate 逻辑不变
```

## 错误处理 (分层兜底)

| 层 | 异常 | 处理 |
|----|------|------|
| `BaseStrategy.evaluate` | filter/signals 抛错 | try/except 返回 `[]` |
| `build_indicators` | parquet 读失败/数据不足 | 返回 None, runner 跳过 |
| `runner.run_all` | 某策略整体炸 | try/except 跳过, log, 继续 |
| `morning_scan` 接入 | runner 整体失败 | 回退纯 screener 路径 |
| `sector_momentum` | sector_rotation 返回 None | signals 返回 `[]` |

原则: 策略层是加分项, 任何失败不阻断 morning_scan 主流程.

## 测试策略

### 单元测试 (tests/test_strategies.py)

用 `T_` 前缀测试数据, monkeypatch build_indicators:

- `test_trend_breakout_hit` — 60根末根创新高+量比2 → 1信号 confidence 0.7
- `test_trend_breakout_miss` — 末根没创新高 → []
- `test_oversold_bounce_rsi_threshold` — RSI=29触发, RSI=31不触发
- `test_near_limit_up_dist_to_limit` — 涨8%距涨停2%触发, 距涨停0.1%已封板不触发
- `test_aggregate_multi_strategy` — 同code被2策略命中 → total_confidence=0.7+0.6
- `test_aggregate_sorted` — confidence高排前
- `test_registry_auto_scan` — 新策略文件被扫到
- `test_base_evaluate_swallows_exception` — signals抛错 → evaluate返回[]不传播

### runner 集成测试 (tests/test_strategies_runner.py)

- `test_run_all_with_fake_candidates` — monkeypatch build_indicators, 喂假候选池
- `test_run_all_data_missing` — build_indicators 返回 None 的 code 跳过
- `test_run_top_limit` — top_m=5 最多5个

### 冒烟测试 (tests/smoke/)

- `test_strategies_import` — import 不报错, 5策略都注册

### 回归

- 现有 `tests/` 38 passed 不退化
- `morning_scan --dry-run` 接入后仍正常

### 测试数据隔离

- 假K线用 `T_` 前缀 code
- `build_indicators` 测试 monkeypatch, 不读真实 parquet
- `sector_momentum` 测试 mock `sector_rotation.analyze`

## 实现顺序

1. `signals.py` (纯数据结构, 无依赖)
2. `base.py` (依赖 signals)
3. `registry.py` (依赖 base)
4. `runner.py` (依赖 registry + signals + ohlcv)
5. `__init__.py` (导出)
6. `trend_breakout.py` (恢复, 依赖 base + runner.build_indicators)
7. `oversold_bounce.py` (恢复)
8. `near_limit_up.py` (恢复)
9. `moneyflow_surge.py` (新增, 依赖 base + eastmoney/screener)
10. `sector_momentum.py` (新增, 依赖 base + sector_rotation)
11. 单元测试 + 集成测试
12. morning_scan 接入
13. 回归测试
