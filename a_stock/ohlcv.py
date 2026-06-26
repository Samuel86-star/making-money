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