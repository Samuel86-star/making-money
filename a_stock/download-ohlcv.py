#!/usr/bin/env python3
"""Download 1y OHLCV for all A-shares via yfinance, cache per-stock parquet.

Output: data/ohlcv/<code>.parquet (one file per stock, resumable)
"""
import json
import sys
import time
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
LIST = ROOT / "data" / "a_share_list.json"
CACHE = ROOT / "data" / "ohlcv"
CACHE.mkdir(parents=True, exist_ok=True)
BATCH = 80
PERIOD = "1y"


def yahoo_symbol(code: str) -> str:
    """6xxxxx → .SS (Shanghai); others → .SZ (Shenzhen)."""
    return f"{code}.SS" if code.startswith("6") else f"{code}.SZ"


def main():
    if not LIST.exists():
        print(f"Missing {LIST}. Run py/fetch-ashare-list.py first.")
        sys.exit(1)

    stocks = json.loads(LIST.read_text())["stocks"]
    codes = [s["code"] for s in stocks]
    todo = [c for c in codes if not (CACHE / f"{c}.parquet").exists()]
    done = len(codes) - len(todo)
    print(f"Total: {len(codes)}, cached: {done}, to download: {len(todo)}")

    if not todo:
        print("Nothing to do.")
        return

    total_batches = (len(todo) + BATCH - 1) // BATCH
    for i in range(0, len(todo), BATCH):
        batch_codes = todo[i:i + BATCH]
        symbols = [yahoo_symbol(c) for c in batch_codes]
        batch_no = i // BATCH + 1
        try:
            data = yf.download(symbols, period=PERIOD, auto_adjust=True,
                               progress=False, threads=True, group_by="ticker")
            saved = 0
            for code, sym in zip(batch_codes, symbols):
                try:
                    if len(symbols) == 1:
                        df = data
                    else:
                        # yfinance multi-ticker columns: top level = ticker
                        if sym not in data.columns.get_level_values(0):
                            continue
                        df = data[sym]
                    if df is None or df.empty or "Volume" not in df.columns:
                        continue
                    df = df.dropna(how="all")
                    if df.empty:
                        continue
                    df.to_parquet(CACHE / f"{code}.parquet")
                    saved += 1
                except Exception:
                    pass
            print(f"  Batch {batch_no}/{total_batches}: saved {saved}/{len(batch_codes)}")
        except Exception as e:
            print(f"  Batch {batch_no}/{total_batches}: FAIL {type(e).__name__}: {e}")
        time.sleep(0.3)

    final = len(list(CACHE.glob("*.parquet")))
    print(f"\nDone. Total cached files: {final}")


if __name__ == "__main__":
    main()
