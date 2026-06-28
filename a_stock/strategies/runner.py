"""策略编排: build_indicators (共享指标) + run_all (跑所有策略) + run_top.
候选池来自 screener.fetch_market_stocks, 已按净流入降序."""
import pandas as pd

from a_stock.ohlcv import load_ohlcv
from a_stock.strategies.signals import aggregate

# 进程内缓存: 同 code 多策略共享指标, 避免重复读 parquet
_INDICATOR_CACHE: dict[str, dict] = {}


def _load_ohlcv(code: str):
    """封装 load_ohlcv, 失败返回 None (供 monkeypatch)."""
    try:
        return load_ohlcv(code)
    except Exception:
        return None


def _rsi(closes: pd.Series, period: int = 14) -> float:
    """Wilder RSI (EMA smoothing, alpha=1/period). 数据不足返回 50 (中性)."""
    if len(closes) < period + 1:
        return 50.0
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    # Wilder smoothing: first avg = SMA, subsequent = (prev*(period-1)+cur)/period
    avg_gain = gain.iloc[1:period+1].mean()
    avg_loss = loss.iloc[1:period+1].mean()
    for i in range(period + 1, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gain.iloc[i]) / period
        avg_loss = (avg_loss * (period - 1) + loss.iloc[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))


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
        "change_pct": float((last["close"] - prev["close"]) / prev["close"] * 100)
                       if prev["close"] else 0.0,
        "body_pct": float((last["close"] - last["open"]) / last["open"] * 100)
                     if last["open"] else 0.0,
        "last_open": float(last["open"]),
        "prev_close": float(prev["close"]),
    }
    _INDICATOR_CACHE[code] = ind
    return ind


def clear_cache() -> None:
    """清指标缓存 (测试用)."""
    _INDICATOR_CACHE.clear()


def run_all(candidates: list) -> list:
    """对候选池跑所有策略, 聚合 SignalVote.
    candidates: [{"code","name",...}] 来自 screener, 已按净流入降序.
    注入资金流排名 + 板块门到对应策略实例."""
    from a_stock.strategies.registry import get_all

    # 注入资金流排名 (candidates 顺序即净流入排名)
    rank_map = {c["code"]: i + 1 for i, c in enumerate(candidates) if c.get("code")}
    strategies = get_all()
    for st in strategies:
        if hasattr(st, "_rank"):
            st._rank = rank_map

    all_signals = []
    for c in candidates:
        code = c.get("code", "")
        name = c.get("name", code)
        for st in strategies:
            try:
                sigs = st.evaluate(code, name)
                all_signals.extend(sigs or [])
            except Exception:
                continue  # 单策略整体炸, 跳过继续
    return aggregate(all_signals)


def run_top(candidates: list, top_m: int = 20) -> list:
    """run_all 后取 topM."""
    votes = run_all(candidates)
    return votes[:max(0, top_m)]
