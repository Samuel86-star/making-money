#!/usr/bin/env python3
"""Backtest multiple A-share momentum / volume strategies.

For each (vol_filter, chg_filter) preset, compute next-day return stats.
Compare each to its no-volume-filter baseline.

Reads: data/ohlcv/<code>.parquet
Writes: data/closeout/backtest_volume.json + prints summary
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "ohlcv"
OUT = ROOT / "data" / "closeout" / "backtest_volume.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

VOL_AVG_DAYS = 5
VOL_MULT = 1.5       # 放量 threshold: vol > 5d_avg * VOL_MULT
SHRINK_RATIO = 0.7   # 缩量 threshold: vol < 5d_avg * SHRINK_RATIO

# (vol_filter, chg_filter, label)
# chg_filter: "weak_up"=0<=chg<2, "breakout"=chg>=5, "limit_up"=chg>=9.5, "any"=none
# vol_filter: "expand", "shrink", "any"
STRATEGIES = [
    ("expand",  "weak_up",  f"放量 + 涨幅<2%"),
    ("shrink",  "weak_up",  f"缩量 + 涨幅<2%"),
    ("any",     "weak_up",  f"仅涨幅<2% (基准)"),
    ("expand",  "breakout", f"放量 + 突破(涨幅≥5%)"),
    ("shrink",  "breakout", f"缩量 + 突破(涨幅≥5%)"),
    ("any",     "breakout", f"纯突破(涨幅≥5%) (基准)"),
    ("expand",  "limit_up", f"放量 + 涨停(涨幅≥9.5%)"),
    ("any",     "limit_up", f"纯涨停(涨幅≥9.5%) (基准)"),
]


def chg_mask(chg: pd.Series, kind: str) -> pd.Series:
    if kind == "weak_up":
        return (chg >= 0) & (chg < 2.0)
    if kind == "breakout":
        return chg >= 5.0
    if kind == "limit_up":
        return chg >= 9.5
    return pd.Series(True, index=chg.index)


def vol_mask(vol: pd.Series, vol_avg: pd.Series, kind: str) -> pd.Series:
    if kind == "expand":
        return vol > vol_avg * VOL_MULT
    if kind == "shrink":
        return vol < vol_avg * SHRINK_RATIO
    return pd.Series(True, index=vol.index)


def collect_for_stock(df: pd.DataFrame, vol_filter: str, chg_filter: str) -> list[dict]:
    if len(df) < VOL_AVG_DAYS + 2:
        return []
    close = df["Close"]
    vol = df["Volume"]
    chg = close.pct_change() * 100
    vol_avg = vol.rolling(VOL_AVG_DAYS).mean().shift(1)
    mask = chg_mask(chg, chg_filter) & vol_mask(vol, vol_avg, vol_filter)
    mask = mask.fillna(False)

    out = []
    for i in range(VOL_AVG_DAYS, len(df) - 1):
        if not mask.iloc[i]:
            continue
        c0, c1 = close.iloc[i], close.iloc[i + 1]
        if c0 == 0 or pd.isna(c0):
            continue
        ret = (c1 - c0) / c0 * 100
        out.append({
            "date": df.index[i].strftime("%Y-%m-%d"),
            "chg_today": round(float(chg.iloc[i]), 3),
            "vol_ratio": round(float(vol.iloc[i] / vol_avg.iloc[i]), 2) if vol_avg.iloc[i] else None,
            "next_ret": round(float(ret), 3),
        })
    return out


def summarize(records: list[dict], label: str) -> dict:
    if not records:
        return {"label": label, "n": 0}
    rets = [r["next_ret"] for r in records]
    wins = sum(1 for r in rets if r > 0)
    return {
        "label": label,
        "n": len(rets),
        "win_rate": round(wins / len(rets) * 100, 1),
        "mean": round(float(np.mean(rets)), 3),
        "median": round(float(np.median(rets)), 3),
        "stdev": round(float(np.std(rets)), 3),
        "min": round(float(np.min(rets)), 3),
        "max": round(float(np.max(rets)), 3),
    }


def main():
    files = sorted(CACHE.glob("*.parquet"))
    if not files:
        print(f"No parquet files in {CACHE}. Run py/download-ohlcv.py first.")
        sys.exit(1)
    print(f"Reading {len(files)} stock files...")

    # Collect all signals in one pass per file
    results: dict[tuple[str, str, str], list[dict]] = {s: [] for s in STRATEGIES}
    for f in files:
        try:
            df = pd.read_parquet(f).sort_index()
        except Exception as e:
            print(f"  skip {f.name}: {e}")
            continue
        for strat in STRATEGIES:
            vol_f, chg_f, _ = strat
            sigs = collect_for_stock(df, vol_f, chg_f)
            for s in sigs:
                s["code"] = f.stem
            results[strat].extend(sigs)

    print()
    summaries = []
    for strat in STRATEGIES:
        vol_f, chg_f, label = strat
        s = summarize(results[strat], label)
        summaries.append((strat, s))
        print(f"=== {s['label']} ===")
        if s["n"] == 0:
            print("  (no data)")
        else:
            for k, v in s.items():
                if k != "label":
                    print(f"  {k}: {v}")
        print()

    # Compare each to its "no volume filter" baseline (same chg_filter)
    print("=== 与无放量过滤基准对比 ===")
    for strat, s in summaries:
        vol_f, chg_f, label = strat
        if vol_f == "any" or s["n"] == 0:
            continue
        baseline_key = ("any", chg_f)
        base = next((sm for st, sm in summaries if st[:2] == baseline_key), None)
        if not base or base["n"] == 0:
            continue
        diff = s["mean"] - base["mean"]
        flag = "✓ 优" if diff > 0 else "✗ 差"
        print(f"  {label}: Δ = {diff:+.3f}%  (n={s['n']:,} vs 基准 n={base['n']:,})  {flag}")

    OUT.write_text(json.dumps({
        "config": {"vol_mult": VOL_MULT, "vol_avg_days": VOL_AVG_DAYS,
                   "shrink_ratio": SHRINK_RATIO},
        "results": [
            {"strategy": list(strat), "summary": s}
            for strat, s in summaries
        ],
    }, ensure_ascii=False, indent=2))
    print(f"\nReport: {OUT}")


if __name__ == "__main__":
    main()
