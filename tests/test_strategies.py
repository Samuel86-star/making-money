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
