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


def test_registry_get_all_returns_strategies():
    """registry 扫描目录后, 至少能 import 不报错 (策略文件此时还没建, 只验扫描不炸)."""
    from a_stock.strategies import registry
    registry._scan()  # 此时策略文件未建, 应返回空不报错
    assert isinstance(registry.get_all(), list)


def test_registry_get_unknown_returns_none():
    from a_stock.strategies import registry
    registry._scan()
    assert registry.get("nonexistent_strategy") is None


# ===== Batch B: strategy implementations (Task 7-11) =====

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
