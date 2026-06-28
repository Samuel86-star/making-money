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
