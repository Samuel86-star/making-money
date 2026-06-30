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


def vcp_score(code: str, n_waves: int = 4, lookback: int = 60) -> float:
    """VCP (Volatility Contraction Pattern) 形态就绪度评分, 0-100.

    Minervini VCP: 洗盘时波动越缩越紧 + 量缩 → 突破在即.
    方法 (docs/references/trading-skills-methodology.md 第5条):
    取近 lookback 日, 等分 n_waves 段, 每段算波动幅度 (high-low)/mean.
    收缩 = 后段波动 < 前段. 量缩 = 末段均量 < 首段.
    Score = 收缩比例×60 + 量缩信号×40.

    无数据/数据不足返回 0."""
    try:
        df = load_ohlcv(code)
    except FileNotFoundError:
        return 0.0
    if df is None or len(df) < n_waves * 3:
        return 0.0
    df = df.tail(lookback).reset_index(drop=True)
    seg = len(df) // n_waves
    if seg < 2:
        return 0.0
    highs = df["high"].astype(float)
    lows = df["low"].astype(float)
    closes = df["close"].astype(float)
    vols = df["volume"].astype(float)

    seg_vols = []  # 每段波动幅度
    seg_quant = []  # 每段均量
    for i in range(n_waves):
        s, e = i * seg, (i + 1) * seg if i < n_waves - 1 else len(df)
        hi = highs.iloc[s:e].max()
        lo = lows.iloc[s:e].min()
        mean_c = closes.iloc[s:e].mean() or 1.0
        seg_vols.append((hi - lo) / mean_c)
        seg_quant.append(vols.iloc[s:e].mean())

    # 收缩: 后段 < 前段 的次数
    contractions = sum(1 for i in range(1, n_waves) if seg_vols[i] < seg_vols[i - 1])
    contraction_ratio = contractions / (n_waves - 1)
    # 量缩: 末段 < 首段
    vol_shrink = 1.0 if seg_quant[-1] < seg_quant[0] else 0.0

    score = contraction_ratio * 60 + vol_shrink * 40
    return round(score, 1)
