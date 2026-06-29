"""Tests for py/ohlcv.py — parquet OHLCV loader."""
import a_stock.ohlcv as ohlcv


def test_load_ohlcv_existing():
    df = ohlcv.load_ohlcv("000001")  # known to exist
    assert not df.empty
    assert "close" in df.columns
    assert "date" in df.columns or df.index.name is not None


def test_load_ohlcv_missing():
    try:
        ohlcv.load_ohlcv("999999")
    except FileNotFoundError:
        pass
    else:
        assert False, "should have raised"


def test_list_available_codes():
    codes = ohlcv.list_available_codes()
    assert len(codes) > 5000
    assert "000001" in codes


# === atr() helper (06-29教训: 动态结构止损价 入场价-max(2%,2*ATR)) ===

def test_atr_returns_positive_for_real_code():
    """真实标的有数据 → atr>0."""
    a = ohlcv.atr("000001", period=14)
    assert a is not None
    assert a > 0


def test_atr_none_when_no_parquet():
    """无 parquet → None (不崩)."""
    assert ohlcv.atr("999999", period=14) is None


def test_atr_period_too_long_returns_none():
    """数据不足 period → None."""
    a = ohlcv.atr("000001", period=100000)
    assert a is None


def test_stop_loss_price_clamps_to_2pct_floor():
    """结构止损价 = 入场价 - max(2%, 2*ATR). ATR极小时用2%地板."""
    # 2%地板: 入场10, ATR极小 → 止损=10*0.98=9.8
    sl = ohlcv.struct_stop_loss(entry=10.0, atr_val=0.001, pct_floor=0.02)
    assert abs(sl - 9.8) < 1e-6


def test_stop_loss_price_uses_2atr_when_larger():
    """2*ATR > 2% 时用 2*ATR."""
    # 入场10, ATR=0.2 → 2*ATR=0.4 > 0.2(2%) → 止损=10-0.4=9.6
    sl = ohlcv.struct_stop_loss(entry=10.0, atr_val=0.2, pct_floor=0.02)
    assert abs(sl - 9.6) < 1e-6
