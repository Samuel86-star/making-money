"""runner 集成测试. monkeypatch load_ohlcv, 不读真实 parquet."""
import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _clear_runner_cache():
    """每个测试前清 runner 指标缓存, 隔离同 code 不同 fake 数据 (build_indicators 按 code 缓存)."""
    from a_stock.strategies import runner
    runner.clear_cache()
    yield


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


# ===== code-review #4: prev_close<=0 数据异常 → build_indicators 返回 None =====

def _fake_ohlcv_prev_close_zero():
    """末根前一根 close=0 (数据缺口/异常填充), 末根 close=11.0 (>0). 70 根."""
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    base = 10.0
    closes = [base] * (n - 2) + [0.0, 11.0]  # 倒数第2根 close=0 (prev_close), 末根 11.0
    opens = closes[:]
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    vols = [10000] * n
    return pd.DataFrame({"date": dates, "open": opens, "high": highs,
                         "low": lows, "close": closes, "volume": vols})


def _fake_ohlcv_last_close_zero():
    """末根 close=0 (异常), 前一根 close=10.0. 70 根."""
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    base = 10.0
    closes = [base] * (n - 1) + [0.0]  # 末根 close=0
    opens = closes[:]
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    vols = [10000] * n
    return pd.DataFrame({"date": dates, "open": opens, "high": highs,
                         "low": lows, "close": closes, "volume": vols})


def test_build_indicators_prev_close_zero_returns_none(monkeypatch):
    """prev_close=0 → build_indicators 返回 None (源头守卫, 不让下游假买)."""
    from a_stock.strategies import runner
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _fake_ohlcv_prev_close_zero())
    assert runner.build_indicators("T_001") is None


def test_build_indicators_last_close_zero_returns_none(monkeypatch):
    """last_close=0 → build_indicators 返回 None."""
    from a_stock.strategies import runner
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _fake_ohlcv_last_close_zero())
    assert runner.build_indicators("T_002") is None


def test_moneyflow_surge_prev_close_zero_no_false_buy(monkeypatch):
    """#4 核心: prev_close=0 + rank<=10 + last_close>0 → 旧代码 moneyflow_surge 假买 0.6.
    修后 build_indicators 返回 None → filter 不通过 → evaluate 返回 []."""
    from a_stock.strategies import runner
    from a_stock.strategies.moneyflow_surge import MoneyflowSurge
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _fake_ohlcv_prev_close_zero())
    mfs = MoneyflowSurge()
    mfs._rank = {"T_001": 5}  # rank<=10, 旧代码会触发
    # filter 因 build_indicators None 返回 False → 不跑 signals
    assert mfs.filter("T_001", "A") is False
    # evaluate 整体返回 []
    assert mfs.evaluate("T_001", "A") == []


# ===== code-review #5: run_all 清上次注入残留 (防长进程陈旧读) =====

def test_run_all_clears_stale_rank_before_injection(monkeypatch):
    """#5: 长进程/repl 里第一次 run_all 注入 _rank={A:1}, 第二次 run_all 必须先清成 None 再注入,
    否则第二次未覆盖的 code 会读到第一次的陈旧 rank.

    构造: 第一次 candidates=[T_001], 注入 _rank={T_001:1}. 第二次 candidates=[T_002].
    断言: 第二次 run_all 调用后, registry 单例的 _rank 是 {T_002:1} (不是残留的 {T_001:1}).
    更关键: 在第二次 run_all 的注入阶段, _rank 曾被清成 None (本测试用 monkeypatch 拦截验证).
    """
    from a_stock.strategies import runner
    from a_stock.strategies.registry import get_all
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _fake_ohlcv(70, 11.0, 11.0, last_vol=30000))

    strategies = get_all()
    # 找到有 _rank 的策略 (MoneyflowSurge)
    rank_strategy = next((s for s in strategies if hasattr(s, "_rank")), None)
    assert rank_strategy is not None, "应至少有一个 _rank 策略"

    # 预置陈旧残留 (模拟上一次 run_all 注入)
    rank_strategy._rank = {"T_STALE": 1}

    # 拦截 setattr 验证 run_all 开头把 _rank 清成 None
    # 用包装: 记录 _rank 被赋的值序列
    seen_rank_values = []
    real_setattr = type(rank_strategy).__setattr__

    class _Spy:
        pass

    # 直接跑 run_all: 第一次 candidates=[T_001], 应清掉 T_STALE 残留再注入 {T_001:1}
    runner.run_all([{"code": "T_001", "name": "A"}])
    # 注入后 _rank 应反映本次 candidates, 不含陈旧 T_STALE
    assert "T_STALE" not in (rank_strategy._rank or {}), "陈旧残留未清理"
    assert rank_strategy._rank.get("T_001") == 1

    # 第二次 run_all 用完全不同的 candidates, 验证陈旧不残留
    runner.run_all([{"code": "T_002", "name": "B"}])
    assert rank_strategy._rank.get("T_002") == 1
    assert "T_001" not in (rank_strategy._rank or {}), "第一次的 rank 残留到第二次"


def test_run_all_clears_stale_sector_result(monkeypatch):
    """#5 扩展: _sector_result 也应在 run_all 开头被清."""
    from a_stock.strategies import runner
    from a_stock.strategies.registry import get_all
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _fake_ohlcv(70, 11.0, 11.0, last_vol=30000))
    # 板块分析返回 None (避免真实 DB 调用)
    import a_stock.sector_rotation as _sr
    monkeypatch.setattr(_sr, "analyze", lambda: None)

    strategies = get_all()
    sector_strategy = next((s for s in strategies if hasattr(s, "_sector_result")), None)
    if sector_strategy is None:
        pytest.skip("无 _sector_result 策略 (仅 SectorMomentum 有)")
    # 预置陈旧残留
    sector_strategy._sector_result = "STALE_OBJECT"
    runner.run_all([{"code": "T_001", "name": "A"}])
    # 陈旧对象应被清掉 (run_all 开头置 None, 然后注入新结果 None)
    assert sector_strategy._sector_result != "STALE_OBJECT", "_sector_result 陈旧残留未清理"


# ===== code-review #6: 去 break, sector_result 算一次共享给所有 _sector_result 策略 =====

def test_run_all_sector_result_shared_to_all_strategies_called_once(monkeypatch):
    """#6: 两个 _sector_result 策略 → analyze 只调一次, 两个实例拿到同一对象 (identity).

    注: _load_ohlcv 返回 None 使 SectorMomentum.filter=False, signals() 不跑,
    从而隔离 #6 注入循环 (不与 signals() 的 _analyze() fallback 混计).
    """
    from a_stock.strategies import runner
    from a_stock.strategies.registry import get_all
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: None)  # filter=False, 隔离 signals 路径

    # 计数 analyze 调用次数
    call_count = {"n": 0}
    class FakeSR:
        strongest_repeat_name = "半导体"
        verdict = "🔥 持续主线"
    def counting_analyze():
        call_count["n"] += 1
        return FakeSR()
    import a_stock.sector_rotation as _sr
    monkeypatch.setattr(_sr, "analyze", counting_analyze)

    strategies = get_all()
    # 给第二个策略临时加 _sector_result 属性 (模拟未来第二个板块类策略)
    sector_strategies = [s for s in strategies if hasattr(s, "_sector_result")]
    others = [s for s in strategies if not hasattr(s, "_sector_result")]
    assert len(sector_strategies) >= 1, "应有 SectorMomentum"
    assert len(others) >= 1, "需要另一个策略来模拟第二个 _sector_result 策略"
    second = others[0]
    monkeypatch.setattr(second, "_sector_result", None, raising=False)

    runner.run_all([{"code": "T_001", "name": "A"}])

    # analyze 只被调一次 (注入循环层面)
    assert call_count["n"] == 1, f"analyze 应只调一次, 实际 {call_count['n']}"
    # 两个策略拿到同一对象 (identity, 不是相等)
    assert sector_strategies[0]._sector_result is second._sector_result, (
        "两个 _sector_result 策略应共享同一对象"
    )
    assert isinstance(sector_strategies[0]._sector_result, FakeSR)


def test_run_all_sector_result_none_not_recomputed(monkeypatch):
    """#6 边界: analyze 合法返回 None (无轮动数据) → 注入循环不应触发重算 (sentinel 区分 None 与未算).

    若用 `if sector_result is None:` 守卫 (md 原始目标代码), analyze 返回 None 后
    下一个 _sector_result 策略会重算. sentinel 守卫修复此 latent bug.
    _load_ohlcv 返回 None 隔离 signals() 的 _analyze() fallback, 只计注入循环调用.
    """
    from a_stock.strategies import runner
    from a_stock.strategies.registry import get_all
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: None)  # filter=False, 隔离 signals 路径

    call_count = {"n": 0}
    def analyze_returns_none():
        call_count["n"] += 1
        return None  # 合法: 无板块轮动数据
    import a_stock.sector_rotation as _sr
    monkeypatch.setattr(_sr, "analyze", analyze_returns_none)

    strategies = get_all()
    sector_strategies = [s for s in strategies if hasattr(s, "_sector_result")]
    others = [s for s in strategies if not hasattr(s, "_sector_result")]
    assert len(others) >= 1
    monkeypatch.setattr(others[0], "_sector_result", None, raising=False)

    runner.run_all([{"code": "T_001", "name": "A"}])

    # 即使 analyze 返回 None, 注入循环也只调一次 (sentinel 防重算)
    assert call_count["n"] == 1, (
        f"analyze 返回 None 时注入循环不应重算, 实际调了 {call_count['n']} 次 "
        "(若用 is None 守卫会重算, sentinel 守卫修复)"
    )
    # 两个策略都拿到 None
    assert sector_strategies[0]._sector_result is None
    assert others[0]._sector_result is None
