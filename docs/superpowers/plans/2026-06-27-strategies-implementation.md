# strategies/ 策略模块实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 strategies/ 多策略信号矩阵 (Signal Bridge), 接入 morning_scan 做候选发现层.

**Architecture:** 5 策略各自产 Signal → runner 聚合 SignalVote → topM 送 morning_scan 做 scorers 5维评分确认. 策略=发现, 评分=确认, 不重叠. 任何策略失败不阻断主流程.

**Tech Stack:** Python 3.12+, pandas, parquet (ohlcv), ABC dataclass, pytest.

**关键接口事实 (已核实代码):**
- `load_ohlcv(code)` 返回 DataFrame, 列名**小写** `open/high/low/close/volume`, 含 `date` 列
- `fetch_market_stocks(top_n)` 返回 `[{"code","name","change_pct","net_flow"}]`, 已按净流入降序
- `sector_rotation.analyze()` 返回 `RotationResult(strongest_repeat_name, current_leader, current_streak_days, verdict, ...)`, verdict ∈ {"持续主线","轮动","衰退",""}
- `sectors.py` **无板块→成分股接口**. sector_momentum 改用 verdict 作市场门 + 候选 change_pct (不依赖成分股归属)

**设计偏离记录:** spec §5 sector_momentum 原设计需板块成分股, 实际无此接口. 改为: verdict=="持续主线" 且候选 change_pct>3% 时触发. 逻辑等价于"主线确立时, 强势候选获动量加分", 不需要成分股映射.

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `a_stock/strategies/signals.py` | Signal + SignalVote dataclass, aggregate() |
| `a_stock/strategies/base.py` | StrategyMeta, BaseStrategy (filter/signals/evaluate), limit_pct |
| `a_stock/strategies/registry.py` | 目录反射自动注册, get_all/get/list_strategies |
| `a_stock/strategies/runner.py` | build_indicators, run_all, run_top |
| `a_stock/strategies/__init__.py` | 导出 |
| `a_stock/strategies/trend_breakout.py` | 趋势突破 0.7 |
| `a_stock/strategies/oversold_bounce.py` | 超跌反弹 0.5 |
| `a_stock/strategies/near_limit_up.py` | 逼近涨停 0.6 |
| `a_stock/strategies/moneyflow_surge.py` | 资金流异动 0.6 |
| `a_stock/strategies/sector_momentum.py` | 板块动量 0.5 |
| `tests/test_strategies.py` | 单元测试 |
| `tests/test_strategies_runner.py` | runner 集成测试 |
| `tests/smoke/test_strategies_smoke.py` | 冒烟测试 |
| `a_stock/morning_scan.py` | 接入 runner (修改) |

---

## Task 1: signals.py (Signal + SignalVote + aggregate)

**Files:**
- Create: `a_stock/strategies/signals.py`
- Test: `tests/test_strategies.py`

- [ ] **Step 1: 写失败测试 — Signal 基本字段 + aggregate 聚合**

Create `tests/test_strategies.py`:

```python
"""strategies/ 单元测试. T_ 前缀测试数据, 不碰真实持仓."""
from a_stock.strategies.signals import Signal, SignalVote, aggregate


def test_signal_fields():
    s = Signal(code="T_001", name="TEST", action="buy", confidence=0.7,
               strategy="trend_breakout", reason="突破")
    assert s.code == "T_001"
    assert s.action == "buy"
    assert s.confidence == 0.7
    assert s.meta is None


def test_aggregate_multi_strategy_same_code():
    """同 code 被 2 策略命中 → total_confidence = 0.7+0.6."""
    sigs = [
        Signal("T_001", "A", "buy", 0.7, "trend_breakout", "突破"),
        Signal("T_001", "A", "buy", 0.6, "moneyflow_surge", "资金"),
    ]
    votes = aggregate(sigs)
    assert len(votes) == 1
    assert votes[0].code == "T_001"
    assert abs(votes[0].total_confidence - 1.3) < 1e-9
    assert set(votes[0].strategies) == {"trend_breakout", "moneyflow_surge"}


def test_aggregate_sorted_by_confidence_desc():
    sigs = [
        Signal("T_002", "B", "buy", 0.5, "oversold_bounce", "超跌"),
        Signal("T_001", "A", "buy", 0.7, "trend_breakout", "突破"),
    ]
    votes = aggregate(sigs)
    assert votes[0].code == "T_001"  # 0.7 > 0.5
    assert votes[1].code == "T_002"


def test_aggregate_ignores_non_buy():
    sigs = [
        Signal("T_001", "A", "hold", 0.9, "x", "观望"),
        Signal("T_001", "A", "buy", 0.7, "y", "买"),
    ]
    votes = aggregate(sigs)
    assert len(votes) == 1
    assert abs(votes[0].total_confidence - 0.7) < 1e-9


def test_aggregate_top_reason_is_highest_confidence():
    sigs = [
        Signal("T_001", "A", "buy", 0.5, "low", "弱理由"),
        Signal("T_001", "A", "buy", 0.7, "high", "强理由"),
    ]
    votes = aggregate(sigs)
    assert votes[0].top_reason == "强理由"


def test_aggregate_empty():
    assert aggregate([]) == []
```

- [ ] **Step 2: 跑测试验证失败**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v`
Expected: FAIL (ModuleNotFoundError: a_stock.strategies.signals)

- [ ] **Step 3: 实现 signals.py**

Create `a_stock/strategies/signals.py`:

```python
"""策略信号数据结构 + 聚合.
Signal: 单策略对单标的的信号.
SignalVote: 同标的多策略信号聚合, 按 total_confidence 排序."""
from dataclasses import dataclass, field


@dataclass
class Signal:
    code: str
    name: str
    action: str            # buy / sell / hold
    confidence: float      # 0.0 ~ 1.0
    strategy: str          # 来源策略名
    reason: str
    meta: dict = None


@dataclass
class SignalVote:
    code: str
    name: str
    total_confidence: float
    strategies: list = field(default_factory=list)
    signals: list = field(default_factory=list)
    top_reason: str = ""


def aggregate(signals: list) -> list:
    """按 code 聚合 buy 信号, total_confidence 降序."""
    by_code: dict[str, SignalVote] = {}
    for s in signals:
        if s.action != "buy":
            continue
        if s.code not in by_code:
            by_code[s.code] = SignalVote(
                code=s.code, name=s.name, total_confidence=0.0,
                strategies=[], signals=[], top_reason=s.reason,
            )
        v = by_code[s.code]
        v.total_confidence += s.confidence
        v.strategies.append(s.strategy)
        v.signals.append(s)
        # top_reason 取当前最高 confidence 那条
        if s.confidence >= max(sig.confidence for sig in v.signals):
            v.top_reason = s.reason
    return sorted(by_code.values(), key=lambda v: -v.total_confidence)
```

- [ ] **Step 4: 跑测试验证通过**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add a_stock/strategies/signals.py tests/test_strategies.py
git commit -m "feat(strategies): Signal + SignalVote + aggregate"
```

---

## Task 2: base.py (StrategyMeta + BaseStrategy + limit_pct)

**Files:**
- Create: `a_stock/strategies/base.py`
- Test: `tests/test_strategies.py` (追加)

- [ ] **Step 1: 追加失败测试 — limit_pct + BaseStrategy.evaluate 兜底**

Append to `tests/test_strategies.py`:

```python
from a_stock.strategies.base import StrategyMeta, BaseStrategy, limit_pct


def test_limit_pct_main_board():
    assert limit_pct("600276") == 10.0
    assert limit_pct("000001") == 10.0


def test_limit_pct_gem_star():
    assert limit_pct("300059") == 20.0  # 创业板
    assert limit_pct("688981") == 20.0  # 科创板


def test_limit_pct_etf():
    # 60/68 开头按 20%, ETF 5/1 开头主板 10%
    assert limit_pct("515650") == 10.0


def test_base_evaluate_swallows_exception():
    """signals 抛错 → evaluate 返回 [], 不传播."""
    class BoomStrategy(BaseStrategy):
        META = StrategyMeta("boom", 0.5, "炸")
        def filter(self, code, name):
            return True
        def signals(self, code, name):
            raise RuntimeError("炸了")

    sigs = BoomStrategy().evaluate("T_001", "X")
    assert sigs == []


def test_base_evaluate_filter_blocks_signals():
    """filter False → 不跑 signals."""
    class FilterStrategy(BaseStrategy):
        META = StrategyMeta("filt", 0.5, "筛")
        called = False
        def filter(self, code, name):
            return False
        def signals(self, code, name):
            FilterStrategy.called = True
            return []

    FilterStrategy().evaluate("T_001", "X")
    assert FilterStrategy.called is False
```

- [ ] **Step 2: 跑测试验证失败**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v -k "limit_pct or base_evaluate"`
Expected: FAIL (ImportError: a_stock.strategies.base)

- [ ] **Step 3: 实现 base.py**

Create `a_stock/strategies/base.py`:

```python
"""策略基类: META + filter + signals 三段式 (抄 tickflow builtin).
新增策略零成本: 继承 BaseStrategy, 声明 META, 实现 filter/signals."""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from a_stock.strategies.signals import Signal


@dataclass
class StrategyMeta:
    name: str
    confidence: float
    description: str


class BaseStrategy(ABC):
    """三段式模板: filter 初筛 → signals 产信号. evaluate 模板方法兜底异常."""
    META: StrategyMeta  # 子类必须声明

    @abstractmethod
    def filter(self, code: str, name: str) -> bool:
        """初筛: 标的适不适合本策略."""

    @abstractmethod
    def signals(self, code: str, name: str) -> list:
        """产信号: 满足条件返回 Signal[], 否则空列表."""

    def evaluate(self, code: str, name: str) -> list:
        """模板方法: filter 通过才跑 signals, 异常兜底返回 []."""
        try:
            if not self.filter(code, name):
                return []
            return self.signals(code, name) or []
        except Exception:
            return []


def limit_pct(code: str) -> float:
    """涨停幅度 %. 创业板(300)/科创板(688) 20%, 主板(含ETF) 10%."""
    if code.startswith(("300", "688")):
        return 20.0
    return 10.0
```

- [ ] **Step 4: 跑测试验证通过**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v`
Expected: 11 passed (6 + 5)

- [ ] **Step 5: 提交**

```bash
git add a_stock/strategies/base.py tests/test_strategies.py
git commit -m "feat(strategies): BaseStrategy 三段式 + limit_pct"
```

---

## Task 3: runner.build_indicators (共享指标计算)

**Files:**
- Create: `a_stock/strategies/runner.py` (部分)
- Test: `tests/test_strategies_runner.py`

- [ ] **Step 1: 写失败测试 — build_indicators 返回指标 dict / None**

Create `tests/test_strategies_runner.py`:

```python
"""runner 集成测试. monkeypatch load_ohlcv, 不读真实 parquet."""
import pandas as pd
import pytest


def _fake_ohlcv(n=70, last_close=10.0, last_high=None, last_vol=20000, rsi_seed=50):
    """造 n 根 K线. 末根可控."""
    import numpy as np
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    base = 10.0
    closes = [base + i * 0.01 for i in range(n - 1)] + [last_close]
    highs = [c + 0.1 for c in closes[:-1]] + [(last_high or last_close + 0.1)]
    lows = [c - 0.1 for c in closes]
    opens = closes[:]
    vols = [10000] * (n - 1) + [last_vol]
    df = pd.DataFrame({"date": dates, "open": opens, "high": highs,
                       "low": lows, "close": closes, "volume": vols})
    return df


def test_build_indicators_returns_dict(monkeypatch):
    from a_stock.strategies import runner
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _fake_ohlcv(70, 11.0, 11.0))
    ind = runner.build_indicators("T_001")
    assert ind is not None
    assert "df" in ind and "ma60" in ind and "rsi" in ind
    assert "high_60d" in ind and "vol_ratio" in ind
    assert "last_close" in ind and "change_pct" in ind


def test_build_indicators_insufficient_data_returns_none(monkeypatch):
    """不足 60 根 → None."""
    from a_stock.strategies import runner
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _fake_ohlcv(40))
    assert runner.build_indicators("T_001") is None


def test_build_indicators_missing_parquet_returns_none(monkeypatch):
    from a_stock.strategies import runner
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: None)
    assert runner.build_indicators("T_999") is None
```

- [ ] **Step 2: 跑测试验证失败**

Run: `.venv/bin/python -m pytest tests/test_strategies_runner.py -v`
Expected: FAIL (ModuleNotFoundError: a_stock.strategies.runner)

- [ ] **Step 3: 实现 runner.py (build_indicators 部分)**

Create `a_stock/strategies/runner.py`:

```python
"""策略编排: build_indicators (共享指标) + run_all (跑所有策略) + run_top.
候选池来自 screener.fetch_market_stocks, 已按净流入降序."""
import pandas as pd

from a_stock.ohlcv import load_ohlcv
from a_stock.strategies.signals import Signal, SignalVote, aggregate

# 进程内缓存: 同 code 多策略共享指标, 避免重复读 parquet
_INDICATOR_CACHE: dict[str, dict] = {}


def _load_ohlcv(code: str):
    """封装 load_ohlcv, 失败返回 None (供 monkeypatch)."""
    try:
        return load_ohlcv(code)
    except Exception:
        return None


def _rsi(closes: pd.Series, period: int = 14) -> float:
    """Wilder RSI. 数据不足返回 50 (中性)."""
    if len(closes) < period + 1:
        return 50.0
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if pd.notna(val) else 50.0


def build_indicators(code: str) -> dict | None:
    """读 ohlcv, 算共享指标. 数据不足返回 None.
    返回 {df, ma60, rsi, high_60d, vol_ratio, last_close, change_pct}."""
    if code in _INDICATOR_CACHE:
        return _INDICATOR_CACHE[code]
    df = _load_ohlcv(code)
    if df is None or len(df) < 60:
        return None
    closes = df["close"]
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last
    vol_ma5 = df["volume"].iloc[-6:-1].mean() if len(df) >= 6 else df["volume"].mean()
    ind = {
        "df": df,
        "ma60": float(closes.rolling(60).mean().iloc[-1]),
        "rsi": _rsi(closes),
        "high_60d": float(df["high"].iloc[-60:].max()),
        "vol_ratio": float(last["volume"] / vol_ma5) if vol_ma5 else 0.0,
        "last_close": float(last["close"]),
        "change_pct": float((last["close"] - last["open"]) / last["open"] * 100)
                       if last["open"] else 0.0,
        "last_open": float(last["open"]),
        "prev_close": float(prev["close"]),
    }
    _INDICATOR_CACHE[code] = ind
    return ind


def clear_cache() -> None:
    """清指标缓存 (测试用)."""
    _INDICATOR_CACHE.clear()
```

- [ ] **Step 4: 跑测试验证通过**

Run: `.venv/bin/python -m pytest tests/test_strategies_runner.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add a_stock/strategies/runner.py tests/test_strategies_runner.py
git commit -m "feat(strategies): runner.build_indicators 共享指标"
```

---

## Task 4: registry.py (自动注册)

**Files:**
- Create: `a_stock/strategies/registry.py`
- Test: `tests/test_strategies.py` (追加)

- [ ] **Step 1: 写失败测试 — 注册扫描**

Append to `tests/test_strategies.py`:

```python
def test_registry_get_all_returns_strategies():
    """registry 扫描目录后, 至少能 import 不报错 (策略文件此时还没建, 只验扫描不炸)."""
    from a_stock.strategies import registry
    registry._scan()  # 此时策略文件未建, 应返回空不报错
    assert isinstance(registry.get_all(), list)


def test_registry_get_unknown_returns_none():
    from a_stock.strategies import registry
    registry._scan()
    assert registry.get("nonexistent_strategy") is None
```

- [ ] **Step 2: 跑测试验证失败**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v -k registry`
Expected: FAIL (ImportError: a_stock.strategies.registry)

- [ ] **Step 3: 实现 registry.py**

Create `a_stock/strategies/registry.py`:

```python
"""策略注册表: 目录反射扫描 (抄 KHunter registry 思路, 简化).
新增策略文件自动注册, 不用改这里. 跳过骨架模块 (base/registry/runner/signals)."""
import importlib
import pkgutil

from a_stock.strategies.base import BaseStrategy

_SKIP = {"base", "registry", "runner", "signals"}
_REGISTRY: dict[str, BaseStrategy] = {}


def _scan() -> None:
    """扫描 strategies/ 下所有非下划线非骨架模块, 收集 BaseStrategy 子类实例."""
    _REGISTRY.clear()
    import a_stock.strategies as pkg
    for _, modname, _ in pkgutil.iter_modules(pkg.__path__):
        if modname.startswith("_") or modname in _SKIP:
            continue
        try:
            mod = importlib.import_module(f"a_stock.strategies.{modname}")
        except Exception:
            continue
        for attr in vars(mod).values():
            if (isinstance(attr, type) and issubclass(attr, BaseStrategy)
                    and attr is not BaseStrategy
                    and attr.__module__ == mod.__name__):
                inst = attr()
                _REGISTRY[inst.META.name] = inst


def get_all() -> list:
    if not _REGISTRY:
        _scan()
    return list(_REGISTRY.values())


def get(name: str):
    if not _REGISTRY:
        _scan()
    return _REGISTRY.get(name)


def list_strategies() -> list:
    if not _REGISTRY:
        _scan()
    return list(_REGISTRY.keys())
```

- [ ] **Step 4: 跑测试验证通过**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v`
Expected: 13 passed (11 + 2)

- [ ] **Step 5: 提交**

```bash
git add a_stock/strategies/registry.py tests/test_strategies.py
git commit -m "feat(strategies): registry 目录反射自动注册"
```

---

## Task 5: runner.run_all + run_top

**Files:**
- Modify: `a_stock/strategies/runner.py` (追加 run_all/run_top)
- Test: `tests/test_strategies_runner.py` (追加)

- [ ] **Step 1: 写失败测试 — run_all 聚合 + run_top 截断 + 数据缺失跳过**

Append to `tests/test_strategies_runner.py`:

```python
def test_run_all_with_fake_candidates(monkeypatch):
    """2 个候选, 1 个数据够, runner 跑策略聚合."""
    from a_stock.strategies import runner
    runner.clear_cache()
    # candidate 1 有数据, 2 无数据
    def fake_load(code):
        return _fake_ohlcv(70, 11.0, 11.0, last_vol=30000) if code == "T_001" else None
    monkeypatch.setattr(runner, "_load_ohlcv", fake_load)

    candidates = [{"code": "T_001", "name": "A"}, {"code": "T_002", "name": "B"}]
    votes = runner.run_all(candidates)
    assert isinstance(votes, list)
    # 不假设具体策略命中 (依赖策略实现), 只验返回结构 + T_002 被跳过
    for v in votes:
        assert v.total_confidence > 0


def test_run_all_data_missing_skipped(monkeypatch):
    from a_stock.strategies import runner
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: None)
    votes = runner.run_all([{"code": "T_001", "name": "A"}])
    assert votes == []


def test_run_top_limits_results(monkeypatch):
    from a_stock.strategies import runner
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _fake_ohlcv(70, 11.0, 11.0, last_vol=30000))
    votes = runner.run_top([{"code": "T_001", "name": "A"}], top_m=0)
    assert len(votes) <= 0
```

- [ ] **Step 2: 跑测试验证失败**

Run: `.venv/bin/python -m pytest tests/test_strategies_runner.py -v -k run`
Expected: FAIL (AttributeError: run_all)

- [ ] **Step 3: 追加 run_all + run_top 到 runner.py**

Append to `a_stock/strategies/runner.py`:

```python
def run_all(candidates: list) -> list:
    """对候选池跑所有策略, 聚合 SignalVote.
    candidates: [{"code","name",...}] 来自 screener, 已按净流入降序.
    注入资金流排名 + 板块门到对应策略实例."""
    from a_stock.strategies.registry import get_all

    # 注入资金流排名 (candidates 顺序即净流入排名)
    rank_map = {c["code"]: i + 1 for i, c in enumerate(candidates)}
    strategies = get_all()
    for st in strategies:
        if hasattr(st, "_rank"):
            st._rank = rank_map

    all_signals = []
    for c in candidates:
        code, name = c.get("code", ""), c.get("name", code)
        for st in strategies:
            try:
                sigs = st.evaluate(code, name)
                all_signals.extend(sigs or [])
            except Exception:
                continue  # 单策略整体炸, 跳过继续
    return aggregate(all_signals)


def run_top(candidates: list, top_m: int = 20) -> list:
    """run_all 后取 topM."""
    votes = run_all(candidates)
    return votes[:max(0, top_m)]
```

- [ ] **Step 4: 跑测试验证通过**

Run: `.venv/bin/python -m pytest tests/test_strategies_runner.py -v`
Expected: 6 passed (3 + 3)

- [ ] **Step 5: 提交**

```bash
git add a_stock/strategies/runner.py tests/test_strategies_runner.py
git commit -m "feat(strategies): runner.run_all + run_top 编排"
```

---

## Task 6: __init__.py 导出

**Files:**
- Create: `a_stock/strategies/__init__.py`
- Test: 无 (冒烟测试 Task 11 覆盖)

- [ ] **Step 1: 写 __init__.py**

Create `a_stock/strategies/__init__.py`:

```python
"""策略模块: 策略=信号列组合 (抄 tickflow).
新增策略零成本: 组合已有信号列. 导出公共接口."""
from a_stock.strategies.signals import Signal, SignalVote, aggregate
from a_stock.strategies.runner import run_all, run_top, build_indicators
from a_stock.strategies.registry import get_all, get, list_strategies

__all__ = [
    "Signal", "SignalVote", "aggregate",
    "run_all", "run_top", "build_indicators",
    "get_all", "get", "list_strategies",
]
```

- [ ] **Step 2: 验证 import 不报错**

Run: `.venv/bin/python -c "from a_stock.strategies import Signal, run_all, list_strategies; print('ok', list_strategies())"`
Expected: `ok []` (此时无策略文件, 空列表)

- [ ] **Step 3: 提交**

```bash
git add a_stock/strategies/__init__.py
git commit -m "feat(strategies): __init__ 导出公共接口"
```

---

## Task 7: trend_breakout.py (趋势突破 0.7)

**Files:**
- Create: `a_stock/strategies/trend_breakout.py`
- Test: `tests/test_strategies.py` (追加)

- [ ] **Step 1: 写失败测试 — 命中/未命中**

Append to `tests/test_strategies.py`:

```python
def test_trend_breakout_hit(monkeypatch):
    """末根创60日新高 + 站上ma60 + 量比≥2 → 1信号 0.7."""
    from a_stock.strategies import runner
    from a_stock.strategies.trend_breakout import TrendBreakout
    runner.clear_cache()
    # 60根递增, 末根创新高, 末根量 30000 (5日均 10000 → 量比3)
    monkeypatch.setattr(runner, "_load_ohlcv",
                        lambda c: _make_breakout_ohlcv(hit=True))
    sigs = TrendBreakout().signals("T_001", "A")
    assert len(sigs) == 1
    assert sigs[0].confidence == 0.7
    assert sigs[0].strategy == "trend_breakout"


def test_trend_breakout_miss_no_new_high(monkeypatch):
    from a_stock.strategies import runner
    from a_stock.strategies.trend_breakout import TrendBreakout
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv",
                        lambda c: _make_breakout_ohlcv(hit=False))
    assert TrendBreakout().signals("T_001", "A") == []


def test_trend_breakout_filter_data_too_short(monkeypatch):
    from a_stock.strategies import runner
    from a_stock.strategies.trend_breakout import TrendBreakout
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_short_ohlcv())
    assert TrendBreakout().filter("T_001", "A") is False


def _make_breakout_ohlcv(hit: bool):
    """70根. hit=True: 末根创新高+量比大; hit=False: 末根不创新高."""
    import pandas as pd
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    closes = [10.0 + i * 0.01 for i in range(n - 1)]
    last_close = 11.0 if hit else 10.0  # hit 超过前面所有
    closes.append(last_close)
    highs = [c + 0.05 for c in closes[:-1]] + [last_close + 0.1]
    df = pd.DataFrame({"date": dates, "open": closes[:],
                       "high": highs, "low": [c - 0.05 for c in closes],
                       "close": closes, "volume": [10000] * (n - 1) + [30000]})
    return df


def _make_short_ohlcv():
    import pandas as pd
    n = 40
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    closes = [10.0] * n
    return pd.DataFrame({"date": dates, "open": closes, "high": closes,
                         "low": closes, "close": closes, "volume": [10000] * n})
```

- [ ] **Step 2: 跑测试验证失败**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v -k trend_breakout`
Expected: FAIL (ImportError: trend_breakout)

- [ ] **Step 3: 实现 trend_breakout.py**

Create `a_stock/strategies/trend_breakout.py`:

```python
"""趋势突破策略 (抄 tickflow trend_breakout.py).
触发: close>ma60 + 60日新高 + 量比≥2. confidence 0.7."""
from a_stock.strategies.base import BaseStrategy, StrategyMeta
from a_stock.strategies.runner import build_indicators
from a_stock.strategies.signals import Signal


class TrendBreakout(BaseStrategy):
    META = StrategyMeta("trend_breakout", 0.7, "趋势突破: 站上60日线+60日新高+量比≥2")

    def filter(self, code, name):
        ind = build_indicators(code)
        return ind is not None and len(ind["df"]) >= 60

    def signals(self, code, name):
        ind = build_indicators(code)
        last = ind["df"].iloc[-1]
        cond = (
            last["close"] > ind["ma60"]
            and last["close"] >= ind["high_60d"]
            and ind["vol_ratio"] >= 2.0
        )
        if cond:
            return [Signal(code, name, "buy", 0.7, "trend_breakout",
                           f"突破60日新高{ind['high_60d']:.2f} 量比{ind['vol_ratio']:.1f}",
                           {"price": ind["last_close"], "ma60": ind["ma60"]})]
        return []
```

- [ ] **Step 4: 跑测试验证通过**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v -k trend_breakout`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add a_stock/strategies/trend_breakout.py tests/test_strategies.py
git commit -m "feat(strategies): trend_breakout 趋势突破"
```

---

## Task 8: oversold_bounce.py (超跌反弹 0.5)

**Files:**
- Create: `a_stock/strategies/oversold_bounce.py`
- Test: `tests/test_strategies.py` (追加)

- [ ] **Step 1: 写失败测试 — RSI 阈值边界**

Append to `tests/test_strategies.py`:

```python
def test_oversold_bounce_hit(monkeypatch):
    """RSI<30 + 收阳 + 量比≥1.2 → 1信号 0.5."""
    from a_stock.strategies import runner
    from a_stock.strategies.oversold_bounce import OversoldBounce
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_rsi_ohlcv(rsi_below_30=True))
    sigs = OversoldBounce().signals("T_001", "A")
    assert len(sigs) == 1
    assert sigs[0].confidence == 0.5


def test_oversold_bounce_miss_rsi_high(monkeypatch):
    from a_stock.strategies import runner
    from a_stock.strategies.oversold_bounce import OversoldBounce
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_rsi_ohlcv(rsi_below_30=False))
    assert OversoldBounce().signals("T_001", "A") == []


def _make_rsi_ohlcv(rsi_below_30: bool):
    """构造让 RSI<30 (连跌) 或 RSI 高 (连涨) 的序列. 末根收阳 + 量比大."""
    import pandas as pd
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    if rsi_below_30:
        # 前 69 根持续下跌, 末根反弹收阳
        closes = [20.0 - i * 0.2 for i in range(n - 1)] + [13.0]
        opens = closes[:]
        opens[-1] = 12.5  # 末根开低于收, 收阳
    else:
        closes = [10.0 + i * 0.1 for i in range(n - 1)] + [17.0]
        opens = closes[:]
        opens[-1] = 16.5
    highs = [max(o, c) + 0.05 for o, c in zip(opens, closes)]
    lows = [min(o, c) - 0.05 for o, c in zip(opens, closes)]
    vols = [10000] * (n - 1) + [15000]  # 量比 1.5
    return pd.DataFrame({"date": dates, "open": opens, "high": highs,
                         "low": lows, "close": closes, "volume": vols})
```

- [ ] **Step 2: 跑测试验证失败**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v -k oversold`
Expected: FAIL (ImportError)

- [ ] **Step 3: 实现 oversold_bounce.py**

Create `a_stock/strategies/oversold_bounce.py`:

```python
"""超跌反弹策略 (抄 tickflow oversold_bounce.py).
触发: RSI<30 + 收阳 + 量比≥1.2. confidence 0.5."""
from a_stock.strategies.base import BaseStrategy, StrategyMeta
from a_stock.strategies.runner import build_indicators
from a_stock.strategies.signals import Signal


class OversoldBounce(BaseStrategy):
    META = StrategyMeta("oversold_bounce", 0.5, "超跌反弹: RSI<30+收阳+量比≥1.2")

    def filter(self, code, name):
        return build_indicators(code) is not None

    def signals(self, code, name):
        ind = build_indicators(code)
        last = ind["df"].iloc[-1]
        cond = (
            ind["rsi"] < 30
            and last["close"] > last["open"]   # 收阳
            and ind["vol_ratio"] >= 1.2
        )
        if cond:
            return [Signal(code, name, "buy", 0.5, "oversold_bounce",
                           f"RSI{ind['rsi']:.0f}超跌 量比{ind['vol_ratio']:.1f}",
                           {"price": ind["last_close"], "rsi": ind["rsi"]})]
        return []
```

- [ ] **Step 4: 跑测试验证通过**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v -k oversold`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add a_stock/strategies/oversold_bounce.py tests/test_strategies.py
git commit -m "feat(strategies): oversold_bounce 超跌反弹"
```

---

## Task 9: near_limit_up.py (逼近涨停 0.6)

**Files:**
- Create: `a_stock/strategies/near_limit_up.py`
- Test: `tests/test_strategies.py` (追加)

- [ ] **Step 1: 写失败测试 — 距涨停边界**

Append to `tests/test_strategies.py`:

```python
def test_near_limit_up_hit(monkeypatch):
    """涨8% (主板涨停10%) 距涨停2% → 触发 0.6."""
    from a_stock.strategies import runner
    from a_stock.strategies.near_limit_up import NearLimitUp
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_limit_ohlcv(change_pct=8.0))
    sigs = NearLimitUp().signals("T_600000", "A")  # 主板 10%
    assert len(sigs) == 1
    assert sigs[0].confidence == 0.6


def test_near_limit_up_miss_already_sealed(monkeypatch):
    """涨9.9% 距涨停0.1% → 已封板, 不触发."""
    from a_stock.strategies import runner
    from a_stock.strategies.near_limit_up import NearLimitUp
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_limit_ohlcv(change_pct=9.9))
    assert NearLimitUp().signals("T_600000", "A") == []


def test_near_limit_up_miss_low_gain(monkeypatch):
    """涨5% → 不触发 (需>7%)."""
    from a_stock.strategies import runner
    from a_stock.strategies.near_limit_up import NearLimitUp
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_limit_ohlcv(change_pct=5.0))
    assert NearLimitUp().signals("T_600000", "A") == []


def _make_limit_ohlcv(change_pct: float):
    """末根日内涨幅 = change_pct (close/open-1). 70根."""
    import pandas as pd
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    closes = [10.0] * (n - 1) + [10.0]
    opens = closes[:]
    opens[-1] = 10.0 / (1 + change_pct / 100)  # open 使 close/open-1 = change_pct
    closes[-1] = 10.0
    highs = [max(o, c) + 0.05 for o, c in zip(opens, closes)]
    lows = [min(o, c) - 0.05 for o, c in zip(opens, closes)]
    return pd.DataFrame({"date": dates, "open": opens, "high": highs,
                         "low": lows, "close": closes, "volume": [10000] * n})
```

- [ ] **Step 2: 跑测试验证失败**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v -k near_limit`
Expected: FAIL (ImportError)

- [ ] **Step 3: 实现 near_limit_up.py**

Create `a_stock/strategies/near_limit_up.py`:

```python
"""逼近涨停策略 (抄 tickflow near_limit_up.py).
触发: 涨>7% 且 距涨停<3% (未封板). confidence 0.6.
盘后选股逻辑: 已封板(距涨停≈0)不选, 留次日空间."""
from a_stock.strategies.base import BaseStrategy, StrategyMeta, limit_pct
from a_stock.strategies.runner import build_indicators
from a_stock.strategies.signals import Signal


class NearLimitUp(BaseStrategy):
    META = StrategyMeta("near_limit_up", 0.6, "逼近涨停: 涨>7%+距涨停<3%+未封板")

    def filter(self, code, name):
        return build_indicators(code) is not None

    def signals(self, code, name):
        ind = build_indicators(code)
        change_pct = ind["change_pct"]
        limit = limit_pct(code)
        dist_to_limit = limit - change_pct
        cond = change_pct > 7 and 0 < dist_to_limit < 3
        if cond:
            return [Signal(code, name, "buy", 0.6, "near_limit_up",
                           f"涨{change_pct:.1f}% 距涨停{dist_to_limit:.1f}%",
                           {"price": ind["last_close"], "change_pct": change_pct})]
        return []
```

- [ ] **Step 4: 跑测试验证通过**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v -k near_limit`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add a_stock/strategies/near_limit_up.py tests/test_strategies.py
git commit -m "feat(strategies): near_limit_up 逼近涨停"
```

---

## Task 10: moneyflow_surge.py (资金流异动 0.6)

**Files:**
- Create: `a_stock/strategies/moneyflow_surge.py`
- Test: `tests/test_strategies.py` (追加)

- [ ] **Step 1: 写失败测试 — 排名阈值 + 收涨门**

Append to `tests/test_strategies.py`:

```python
def test_moneyflow_surge_hit_top10(monkeypatch):
    """资金流排名 #5 + 收涨 → 触发 0.6."""
    from a_stock.strategies import runner
    from a_stock.strategies.moneyflow_surge import MoneyflowSurge
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_rising_ohlcv())
    mfs = MoneyflowSurge()
    mfs._rank = {"T_001": 5}
    sigs = mfs.signals("T_001", "A")
    assert len(sigs) == 1
    assert sigs[0].confidence == 0.6


def test_moneyflow_surge_miss_rank_too_low(monkeypatch):
    """排名 #15 (>10) → 不触发."""
    from a_stock.strategies import runner
    from a_stock.strategies.moneyflow_surge import MoneyflowSurge
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_rising_ohlcv())
    mfs = MoneyflowSurge()
    mfs._rank = {"T_001": 15}
    assert mfs.signals("T_001", "A") == []


def test_moneyflow_surge_miss_dropping(monkeypatch):
    """排名 #3 但收跌 → 不触发."""
    from a_stock.strategies import runner
    from a_stock.strategies.moneyflow_surge import MoneyflowSurge
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_falling_ohlcv())
    mfs = MoneyflowSurge()
    mfs._rank = {"T_001": 3}
    assert mfs.signals("T_001", "A") == []


def _make_rising_ohlcv():
    import pandas as pd
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    closes = [10.0 + i * 0.01 for i in range(n - 1)] + [11.0]
    opens = closes[:]
    opens[-1] = 10.5  # 收涨
    return pd.DataFrame({"date": dates, "open": opens, "high": [c+0.1 for c in closes],
                         "low": [c-0.1 for c in closes], "close": closes,
                         "volume": [10000]*n})


def _make_falling_ohlcv():
    import pandas as pd
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    closes = [11.0 - i * 0.01 for i in range(n - 1)] + [10.0]
    opens = closes[:]
    opens[-1] = 10.5  # 收跌 (close 10 < open 10.5)
    return pd.DataFrame({"date": dates, "open": opens, "high": [c+0.1 for c in closes],
                         "low": [c-0.1 for c in closes], "close": closes,
                         "volume": [10000]*n})
```

- [ ] **Step 2: 跑测试验证失败**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v -k moneyflow`
Expected: FAIL (ImportError)

- [ ] **Step 3: 实现 moneyflow_surge.py**

Create `a_stock/strategies/moneyflow_surge.py`:

```python
"""资金流异动策略 (新增).
候选池来自 screener 已按净流入降序. 前10名 + 收涨 → 触发.
_rank 由 runner.run_all 注入 {code: 1-based_rank}."""
from a_stock.strategies.base import BaseStrategy, StrategyMeta
from a_stock.strategies.runner import build_indicators
from a_stock.strategies.signals import Signal


class MoneyflowSurge(BaseStrategy):
    META = StrategyMeta("moneyflow_surge", 0.6, "资金流异动: 净流入top10+收涨")
    _rank: dict = {}  # runner 注入

    def filter(self, code, name):
        return build_indicators(code) is not None

    def signals(self, code, name):
        rank = self._rank.get(code, 999)
        if rank > 10:
            return []
        ind = build_indicators(code)
        # 收涨: 末根 close > 前根 close
        if ind["last_close"] > ind["prev_close"]:
            return [Signal(code, name, "buy", 0.6, "moneyflow_surge",
                           f"资金流排名#{rank} 收涨{ind['change_pct']:+.1f}%",
                           {"price": ind["last_close"], "rank": rank})]
        return []
```

- [ ] **Step 4: 跑测试验证通过**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v -k moneyflow`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add a_stock/strategies/moneyflow_surge.py tests/test_strategies.py
git commit -m "feat(strategies): moneyflow_surge 资金流异动"
```

---

## Task 11: sector_momentum.py (板块动量 0.5)

**Files:**
- Create: `a_stock/strategies/sector_momentum.py`
- Test: `tests/test_strategies.py` (追加)

**注:** 设计偏离 spec — 不依赖板块成分股 (无此接口), 用 sector_rotation verdict 作市场门 + 候选 change_pct.

- [ ] **Step 1: 写失败测试 — verdict 门 + 涨幅**

Append to `tests/test_strategies.py`:

```python
def test_sector_momentum_hit(monkeypatch):
    """verdict=持续主线 + 候选涨4% → 触发 0.5."""
    from a_stock.strategies import runner
    from a_stock.strategies import sector_momentum as sm
    from a_stock.strategies.sector_momentum import SectorMomentum
    runner.clear_cache()
    # mock sector_rotation.analyze
    class FakeSR:
        strongest_repeat_name = "半导体"
        verdict = "持续主线"
    monkeypatch.setattr(sm, "_analyze", lambda: FakeSR())
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_change_ohlcv(4.0))
    sigs = SectorMomentum().signals("T_001", "A")
    assert len(sigs) == 1
    assert sigs[0].confidence == 0.5


def test_sector_momentum_miss_no_mainline(monkeypatch):
    """verdict=轮动 (非持续主线) → 不触发."""
    from a_stock.strategies import runner
    from a_stock.strategies import sector_momentum as sm
    from a_stock.strategies.sector_momentum import SectorMomentum
    runner.clear_cache()
    class FakeSR:
        strongest_repeat_name = "半导体"
        verdict = "轮动"
    monkeypatch.setattr(sm, "_analyze", lambda: FakeSR())
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_change_ohlcv(4.0))
    assert SectorMomentum().signals("T_001", "A") == []


def test_sector_momentum_miss_low_change(monkeypatch):
    """持续主线但涨2% (<3) → 不触发."""
    from a_stock.strategies import runner
    from a_stock.strategies import sector_momentum as sm
    from a_stock.strategies.sector_momentum import SectorMomentum
    runner.clear_cache()
    class FakeSR:
        strongest_repeat_name = "半导体"
        verdict = "持续主线"
    monkeypatch.setattr(sm, "_analyze", lambda: FakeSR())
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_change_ohlcv(2.0))
    assert SectorMomentum().signals("T_001", "A") == []


def test_sector_momentum_no_rotation_data(monkeypatch):
    """analyze 返回 None → 不报错, []."""
    from a_stock.strategies import runner
    from a_stock.strategies import sector_momentum as sm
    from a_stock.strategies.sector_momentum import SectorMomentum
    runner.clear_cache()
    monkeypatch.setattr(sm, "_analyze", lambda: None)
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_change_ohlcv(4.0))
    assert SectorMomentum().signals("T_001", "A") == []


def _make_change_ohlcv(change_pct: float):
    """末根日内涨幅 = change_pct."""
    import pandas as pd
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    closes = [10.0] * n
    opens = closes[:]
    opens[-1] = 10.0 / (1 + change_pct / 100)
    return pd.DataFrame({"date": dates, "open": opens, "high": [c+0.1 for c in closes],
                         "low": [c-0.1 for c in closes], "close": closes,
                         "volume": [10000]*n})
```

- [ ] **Step 2: 跑测试验证失败**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v -k sector_momentum`
Expected: FAIL (ImportError)

- [ ] **Step 3: 实现 sector_momentum.py**

Create `a_stock/strategies/sector_momentum.py`:

```python
"""板块动量策略 (新增).
设计偏离 spec: sectors.py 无板块→成分股接口, 改用 sector_rotation verdict 作市场门.
触发: 轮动 verdict=='持续主线' 且候选日内涨>3%. confidence 0.5.
逻辑: 主线确立时, 强势候选获动量加分."""
from a_stock.strategies.base import BaseStrategy, StrategyMeta
from a_stock.strategies.runner import build_indicators
from a_stock.strategies.signals import Signal


def _analyze():
    """封装 sector_rotation.analyze, 供 monkeypatch."""
    from a_stock.sector_rotation import analyze
    try:
        return analyze()
    except Exception:
        return None


class SectorMomentum(BaseStrategy):
    META = StrategyMeta("sector_momentum", 0.5, "板块动量: 主线确立+候选涨>3%")

    def filter(self, code, name):
        return build_indicators(code) is not None

    def signals(self, code, name):
        sr = _analyze()
        if not sr or getattr(sr, "verdict", "") != "持续主线":
            return []
        ind = build_indicators(code)
        if ind["change_pct"] > 3:
            return [Signal(code, name, "buy", 0.5, "sector_momentum",
                           f"主线{sr.strongest_repeat_name} 候选涨{ind['change_pct']:.1f}%",
                           {"price": ind["last_close"],
                            "main_sector": sr.strongest_repeat_name})]
        return []
```

- [ ] **Step 4: 跑测试验证通过**

Run: `.venv/bin/python -m pytest tests/test_strategies.py -v -k sector_momentum`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add a_stock/strategies/sector_momentum.py tests/test_strategies.py
git commit -m "feat(strategies): sector_momentum 板块动量"
```

---

## Task 12: 冒烟测试 + registry 集成

**Files:**
- Create: `tests/smoke/test_strategies_smoke.py`
- Test: 无 (此即测试)

- [ ] **Step 1: 写冒烟测试 — 5策略全注册 + run_all 不炸**

Create `tests/smoke/test_strategies_smoke.py`:

```python
"""冒烟测试: strategies 导入 + 5策略注册 + run_all 结构正确."""
from a_stock.strategies import list_strategies, run_all, Signal


def test_all_strategies_registered():
    names = set(list_strategies())
    expected = {"trend_breakout", "oversold_bounce", "near_limit_up",
                "moneyflow_surge", "sector_momentum"}
    assert expected.issubset(names), f"missing: {expected - names}"


def test_run_all_empty_candidates():
    """空候选池 → 空列表, 不炸."""
    assert run_all([]) == []


def test_signal_import():
    s = Signal("T_001", "A", "buy", 0.5, "x", "r")
    assert s.code == "T_001"
```

- [ ] **Step 2: 跑冒烟测试**

Run: `.venv/bin/python -m pytest tests/smoke/test_strategies_smoke.py -v`
Expected: 3 passed

- [ ] **Step 3: 跑全部 strategies 测试 + 现有回归**

Run: `.venv/bin/python -m pytest tests/test_strategies.py tests/test_strategies_runner.py tests/smoke/test_strategies_smoke.py -v`
Expected: 全 passed

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 现有 38 passed + 新增, 16 skipped 不变

- [ ] **Step 4: 提交**

```bash
git add tests/smoke/test_strategies_smoke.py
git commit -m "test(strategies): 冒烟测试 5策略注册"
```

---

## Task 13: morning_scan 接入 runner

**Files:**
- Modify: `a_stock/morning_scan.py:31-90` (`_scan_impl` 主流程)
- Test: 手动 dry-run 验证

- [ ] **Step 1: 读 morning_scan 当前 _scan_impl**

Run: `sed -n '31,90p' a_stock/morning_scan.py`

确认插入点: `stocks = fetch_market_stocks(top_n=top_n)` 之后, 评分循环之前.

- [ ] **Step 2: 接入 runner, 策略候选与 screener 候选并集送评分**

Modify `a_stock/morning_scan.py`. 在 `scored = []` (评分循环) 之前, `stocks = fetch_market_stocks(...)` 之后插入策略层:

```python
    # === 策略层 (Signal Bridge): 策略候选 + screener 候选并集 ===
    strategy_codes = set()
    try:
        from a_stock.strategies.runner import run_top
        votes = run_top(stocks, top_m=20)
        strategy_codes = {v.code for v in votes}
        print(f"  策略层产出 {len(strategy_codes)} 只候选 (top confidence)")
        for v in votes[:5]:
            print(f"    {v.name}({v.code}) conf={v.total_confidence:.2f} "
                  f"[{','.join(v.strategies)}] {v.top_reason}")
    except Exception as e:
        print(f"  ⚠ 策略层失败, 回退纯 screener: {e}")
        strategy_codes = set()
```

然后把评分循环的输入从 `stocks` 改为并集. 找到评分循环:

```python
    # 2. 多因子评分
    scored = []
    for s in stocks:
        try:
            ts = score_candidate(s["code"], s.get("name", ""))
```

改为:

```python
    # 2. 多因子评分 — 策略候选 ∪ screener top10
    scored = []
    scored_codes = strategy_codes | {s["code"] for s in stocks[:10]}
    # 建 code→stock 映射 (策略产出的 code 可能不在 screener 前10, 用其 code 查 stock)
    stock_map = {s["code"]: s for s in stocks}
    for code in scored_codes:
        s = stock_map.get(code, {"code": code, "name": code,
                                 "net_flow": 0, "change_pct": 0})
        try:
            ts = score_candidate(s["code"], s.get("name", ""))
            d = to_dict(ts)
            d["net_flow_yi"] = (s.get("net_flow") or 0) / 1e8
            d["change_pct"] = s.get("change_pct", 0)
            scored.append(d)
        except Exception as e:
            print(f"  ⚠ {code} 评分失败: {e}")
```

- [ ] **Step 3: dry-run 验证不炸**

Run: `.venv/bin/python -m a_stock.morning_scan --dry-run`
Expected: 输出含 "策略层产出 N 只候选" 或 "策略层失败, 回退", 不报错

- [ ] **Step 4: 回归测试**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 全 passed, 无退化

- [ ] **Step 5: 提交**

```bash
git add a_stock/morning_scan.py
git commit -m "feat(morning_scan): 接入 strategies runner 策略候选层"
```

---

## Task 14: 最终回归 + 架构图同步缺口表

**Files:**
- 无新文件, 验证为主

- [ ] **Step 1: 全量测试**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 全 passed (38 原有 + 新增 strategies 测试), 16 skipped

- [ ] **Step 2: monitor dry-run 不受影响**

Run: `.venv/bin/python -m a_stock.monitor --dry-run`
Expected: 正常输出 (9规则/5持仓)

- [ ] **Step 3: morning_scan dry-run**

Run: `.venv/bin/python -m a_stock.morning_scan --dry-run`
Expected: 策略层产出 + 评分正常

- [ ] **Step 4: 更新 session 记录**

Update `sessions/2026-06-27-arch-redraw-monitor-strategies.md` 未完成项 → 已完成.

- [ ] **Step 5: 提交收尾**

```bash
git add sessions/2026-06-27-arch-redraw-monitor-strategies.md
git commit -m "docs: strategies/ 实现完成, 更新 session"
```

---

## Self-Review 记录

- **Spec 覆盖**: signals/base/registry/runner/__init__ + 5策略 + 测试 + morning_scan 接入, 全覆盖. sector_momentum 因无成分股接口做了设计偏离, 已在 Task 11 标注.
- **占位符**: 无 TBD/TODO, 所有步骤含完整代码.
- **类型一致**: build_indicators 返回字段 (df/ma60/rsi/high_60d/vol_ratio/last_close/change_pct/last_open/prev_close) 在所有策略一致; Signal 字段一致; _rank 注入在 runner.run_all 和 moneyflow_surge 一致.
- **回归**: Task 12/14 显式跑现有 38 passed 不退化.
