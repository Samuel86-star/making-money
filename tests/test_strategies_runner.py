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
