"""morning_scan Turtle 接入测试.
验证 _turtle_enrich: 命中突破→加total(sys2+8/sys1+5)+标turtle字段; 无突破不变."""
from unittest.mock import patch
from a_stock.morning_scan import _turtle_enrich


def _scored(code, total=60):
    """造一条 scored 候选 dict."""
    return {"code": code, "name": code, "total": total, "level": "观望偏多",
            "net_flow_yi": 0.5, "factors": {}}


def _mock_turtle(signal=None, entry=10.0, stop=9.0, unit=1000, atr=0.5):
    """造 TurtleSignal mock (signal=None 模拟无突破)."""
    from a_stock.turtle import TurtleSignal
    return TurtleSignal(
        code="X", price=10.0, signal=signal,
        dc20_high=9.5, dc20_low=8.0, dc55_high=9.5,
        atr=atr, entry=entry if signal else None,
        stop=stop if signal else None, unit_shares=unit if signal else 0,
        pyramid=[], note="",
    )


def test_turtle_sys2_breakout_boosts_8():
    """sys2(55日)突破 → total +8, 标 turtle 字段."""
    scored = [_scored("T_SYS2", total=60)]
    with patch("a_stock.turtle.analyze", return_value=_mock_turtle("sys2_breakout", entry=10.0, stop=9.0, unit=1000, atr=0.5)):
        _turtle_enrich(scored)
    assert scored[0]["total"] == 68
    assert scored[0]["turtle"]["signal"] == "sys2_breakout"
    assert scored[0]["turtle"]["entry"] == 10.0
    assert scored[0]["turtle"]["unit_shares"] == 1000


def test_turtle_sys1_breakout_boosts_5():
    """sys1(20日)突破 → total +5."""
    scored = [_scored("T_SYS1", total=60)]
    with patch("a_stock.turtle.analyze", return_value=_mock_turtle("sys1_breakout")):
        _turtle_enrich(scored)
    assert scored[0]["total"] == 65
    assert scored[0]["turtle"]["signal"] == "sys1_breakout"


def test_turtle_no_breakout_unchanged():
    """无突破 → total 不变, 无 turtle 字段."""
    scored = [_scored("T_NONE", total=60)]
    with patch("a_stock.turtle.analyze", return_value=_mock_turtle(None)):
        _turtle_enrich(scored)
    assert scored[0]["total"] == 60
    assert "turtle" not in scored[0]


def test_turtle_analyze_none_skips():
    """turtle.analyze 返回 None (无数据) → 不崩, 不变."""
    scored = [_scored("T_NODATA", total=60)]
    with patch("a_stock.turtle.analyze", return_value=None):
        _turtle_enrich(scored)
    assert scored[0]["total"] == 60
    assert "turtle" not in scored[0]


def test_turtle_mixed_candidates():
    """多候选混合: 有突破/无突破/无数据 → 各自正确."""
    scored = [_scored("T_A", 60), _scored("T_B", 60), _scored("T_C", 60)]
    sig_map = {"T_A": _mock_turtle("sys2_breakout"),
               "T_B": _mock_turtle(None),
               "T_C": None}
    with patch("a_stock.turtle.analyze", side_effect=lambda c, **kw: sig_map.get(c)):
        _turtle_enrich(scored)
    assert scored[0]["total"] == 68  # T_A sys2 +8
    assert scored[1]["total"] == 60  # T_B 无突破
    assert scored[2]["total"] == 60  # T_C 无数据


def test_turtle_exception_does_not_crash_scan():
    """turtle.analyze 抛异常 → 该候选跳过, 不影响其他."""
    scored = [_scored("T_ERR", 60), _scored("T_OK", 60)]
    def boom(code, **kw):
        if code == "T_ERR":
            raise RuntimeError("parquet 坏")
        return _mock_turtle("sys1_breakout")
    with patch("a_stock.turtle.analyze", side_effect=boom):
        _turtle_enrich(scored)
    assert scored[0]["total"] == 60  # 异常候选不变
    assert scored[1]["total"] == 65  # T_OK sys1 +5
