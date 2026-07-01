"""turtle 单元测试: Donchian 突破 + 2N 止损 + 1% 单位 + 金字塔."""
from a_stock import turtle


# === Donchian 通道 ===

def test_donchian_excludes_current_day():
    """唐奇安通道: 近 n 日(排除当日) 最高/最低."""
    closes = [10, 11, 12, 13, 14, 9, 20]  # 当日20应被排除
    hi, lo = turtle.donchian(closes, 5)
    assert hi == 14  # max(11,12,13,14,9)
    assert lo == 9


def test_donchian_short_history_returns_current():
    """数据不足 → 返回当日价."""
    closes = [10, 11, 12]
    hi, lo = turtle.donchian(closes, 5)
    assert hi == 12 and lo == 12


# === 突破信号 ===

def test_breakout_sys2_dominates_sys1():
    """55日突破(也满足20日) → sys2 (更强)."""
    closes = [10.0] * 55 + [12.0]  # 55日平台+当日突破
    assert turtle.breakout_signal(closes) == "sys2_breakout"


def test_breakout_sys1_only():
    """仅20日突破(非55日) → sys1."""
    # 构造55日内有高于近20日的值(非55日突破), 但当日>近20日高
    closes = [10.0] * 20 + [13.0] * 35 + [12.5]  # 近20日高=13, 当日12.5<13... 不突破
    # 改: 近20日max=11, 55日内有13但那是35天前; 当日>近20日高且<近55日高 → sys1
    closes = [13.0] * 35 + [10.0] * 20 + [11.5]
    assert turtle.breakout_signal(closes) == "sys1_breakout"


def test_no_breakout_in_range():
    """区间震荡 → None."""
    closes = [10.0 + (i % 5) * 0.1 for i in range(56)]
    assert turtle.breakout_signal(closes) is None


# === 止损/单位/金字塔 ===

def test_turtle_stop_is_entry_minus_2atr():
    """止损 = 入场 - 2×ATR (无地板)."""
    assert turtle.turtle_stop(10.0, 0.4) == 9.2  # 10 - 0.8
    assert turtle.turtle_stop(10.0, None) is None
    assert turtle.turtle_stop(10.0, 0) is None


def test_unit_size_1pct_risk():
    """1Unit = (资本×1%) / (2×ATR), 取整100手."""
    # 资本80000, ATR=0.4 → 风险800/止损0.8=1000股 → 1000//100*100=1000
    assert turtle.unit_size(80000.0, 0.4) == 1000


def test_unit_size_rounds_to_100_lot():
    """A股100股整手."""
    # 资本80000, ATR=1.5 → 800/3=266 → 200股
    assert turtle.unit_size(80000.0, 1.5) == 200


def test_unit_size_zero_when_atr_missing():
    assert turtle.unit_size(80000.0, None) == 0
    assert turtle.unit_size(80000.0, 0) == 0


def test_pyramid_plan_4_units():
    """4Unit金字塔: 首仓+3加仓, 每+0.5N."""
    plan = turtle.pyramid_plan(10.0, 0.4, max_units=4)
    # 加仓价: 10+0.2, 10+0.4, 10+0.6
    assert plan == [10.2, 10.4, 10.6]


def test_pyramid_plan_single_unit_empty():
    """max_units=1 → 无加仓."""
    assert turtle.pyramid_plan(10.0, 0.4, max_units=1) == []


def test_exit_signal_sys1_breaks_10d_low():
    """多头退出 sys1: 跌破10日低."""
    closes = [10, 11, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3]  # 当日3 < 近10日低=4
    assert turtle.exit_signal(closes, sys=1) == "exit_long"


def test_exit_no_signal_above_low():
    closes = [5, 6, 7, 8, 9, 10, 11, 12]
    assert turtle.exit_signal(closes, sys=1) is None
