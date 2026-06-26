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