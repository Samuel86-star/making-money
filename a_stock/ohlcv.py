"""parquet OHLCV 数据读取。"""
from pathlib import Path
import pandas as pd
import a_stock.config as cfg


def load_ohlcv(code: str) -> pd.DataFrame:
    """读 <code>.parquet,返回标准化 DataFrame(date, open, high, low, close, volume)。"""
    path = cfg.OHLCV_DIR / f"{code}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"no parquet for {code}")
    df = pd.read_parquet(path)
    # 标准化列名(原始可能是 DateTime/index)
    df.columns = [c.lower() for c in df.columns]
    if "date" not in df.columns and df.index.name:
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
    if "volume" not in df.columns and "vol" in df.columns:
        df = df.rename(columns={"vol": "volume"})
    return df


def list_available_codes() -> list[str]:
    return sorted([p.stem for p in cfg.OHLCV_DIR.glob("*.parquet")])


def atr(code: str, period: int = 14) -> float | None:
    """ATR(14) — Wilder 平均真实波幅. 无数据/数据不足返回 None.

    TR = max(high-low, |high-prev_close|, |low-prev_close|).
    ATR = 近 period 日 TR 的简单平均 (Wilder 用平滑, 这里简化为 SMA, 趋势止损够用).
    供动态结构止损: 入场价 - max(2%, 2*ATR)."""
    try:
        df = load_ohlcv(code)
    except FileNotFoundError:
        return None
    if len(df) < period + 1:
        return None
    highs = df["high"].astype(float).tolist()
    lows = df["low"].astype(float).tolist()
    closes = df["close"].astype(float).tolist()
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def struct_stop_loss(entry: float, atr_val: float | None,
                     pct_floor: float = 0.02) -> float:
    """结构止损价 = 入场价 - max(pct_floor, 2*ATR).

    ATR 极小时用 pct_floor 地板 (防 ETF 浅止损被洗, 见 docs/knowledge/01).
    ATR 为 None 时仅用 pct_floor."""
    atr_term = (2 * atr_val) if atr_val and atr_val > 0 else 0.0
    drop = max(entry * pct_floor, atr_term)
    return entry - drop
