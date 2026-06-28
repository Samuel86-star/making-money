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
