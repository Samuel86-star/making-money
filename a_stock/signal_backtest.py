"""历史信号回测: 在 parquet 上测 detector 的 forward-return edge.

不用等日记 setup 攒样本 (那是 [A]-[J] 假设的回测, 需满5工作日).
本模块直接验 detector 逻辑有没有 edge: 滑动历史每个交易日T, 跑 detector, 命中则记 T→T+N forward return.
出"信号历史命中N次/胜率/平均回报/相对base rate的edge".

⚠️ 已知偏差:
- 幸存者偏差: parquet 只含现存股 (无退市), A股81-244日窗口偏差小.
- 无前视: detector 只用 ≤T 数据, forward return 用 T→T+N, 干净.
- 交易成本未扣 (滑点/佣金/印花税), 实战 edge 会低一截.
"""
import argparse
import json
from datetime import date
from pathlib import Path
from statistics import median

import a_stock.config as cfg


def backtest_signal(signal_fn, closes: list, vols: list,
                    forward_days: tuple = (5, 10, 20),
                    min_history: int = 60) -> dict:
    """单股滑动回测. 对每个 T (min_history ≤ T < n-max_N), 跑 signal_fn(closes[:T+1], vols[:T+1]).
    命中 (返回真值) 则记 forward return = (close[T+N]-close[T])/close[T].
    返回 {N: [forward_returns]} 原始列表. signal_fn 异常当未命中."""
    results = {N: [] for N in forward_days}
    n = len(closes)
    max_N = max(forward_days)
    for T in range(min_history, n - max_N):
        try:
            fired = signal_fn(closes[:T + 1], vols[:T + 1])
        except Exception:
            fired = False
        if not fired:
            continue
        entry = closes[T]
        for N in forward_days:
            if entry > 0 and T + N < n:
                results[N].append((closes[T + N] - entry) / entry)
    return results


def aggregate_stats(per_stock: list, forward_days: tuple) -> dict:
    """合并多股 {N: [returns]} → {N: {count, wins, win_rate, avg_return, median}}.
    无样本 → None."""
    merged = {N: [] for N in forward_days}
    for r in per_stock:
        for N, rets in r.items():
            if N in merged:
                merged[N].extend(rets)
    stats = {}
    for N, rets in merged.items():
        if not rets:
            stats[N] = None
            continue
        wins = sum(1 for x in rets if x > 0)
        stats[N] = {
            "count": len(rets),
            "wins": wins,
            "win_rate": round(wins / len(rets), 4),
            "avg_return": round(sum(rets) / len(rets), 4),
            "median": round(median(rets), 4),
        }
    return stats


def base_rate(closes: list, vols: list, forward_days: tuple, min_history: int = 60) -> dict:
    """base rate: always-true signal 的 forward return 统计 = 全市场基准."""
    return aggregate_stats(
        [backtest_signal(lambda c, v: True, closes, vols, forward_days, min_history)],
        forward_days,
    )


def edge(signal_avg: float, base_avg: float) -> float:
    """edge = 信号均值 - base均值. 正=信号优于随机."""
    return round(signal_avg - base_avg, 4)


# === 信号包装 (detector → bool signal_fn) ===

def signal_vcp(closes, vols):
    from a_stock.scorers.technical_scorer import _detect_vcp
    return _detect_vcp(closes, vols) is not None


def signal_wyckoff_accumulation(closes, vols):
    from a_stock.scorers.technical_scorer import _detect_wyckoff
    w = _detect_wyckoff(closes, vols)
    return w is not None and w["phase"] == "accumulation"


def signal_wyckoff_distribution(closes, vols):
    from a_stock.scorers.technical_scorer import _detect_wyckoff
    w = _detect_wyckoff(closes, vols)
    return w is not None and w["phase"] == "distribution"


def signal_turtle_sys1(closes, vols):
    from a_stock.turtle import breakout_signal
    return breakout_signal(closes) == "sys1_breakout"


def signal_turtle_sys2(closes, vols):
    from a_stock.turtle import breakout_signal
    return breakout_signal(closes) == "sys2_breakout"


SIGNALS = {
    "VCP(Minervini)": signal_vcp,
    "Wyckoff吸筹": signal_wyckoff_accumulation,
    "Wyckoff派发": signal_wyckoff_distribution,
    "Turtle sys1(20日突破)": signal_turtle_sys1,
    "Turtle sys2(55日突破)": signal_turtle_sys2,
}


def _load_parquet(code: str):
    """加载单只 parquet → (closes, vols). 失败返回 None."""
    f = cfg.OHLCV_DIR / f"{code}.parquet"
    if not f.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(f)
        ccol = "close" if "close" in df.columns else "Close"
        vcol = "volume" if "volume" in df.columns else "Volume"
        closes = df[ccol].astype(float).tolist()
        vols = df[vcol].astype(float).tolist() if vcol in df.columns else [0.0] * len(closes)
        return closes, vols
    except Exception:
        return None


def run_all(forward_days=(5, 10, 20), min_history=80, sample=None) -> dict:
    """全市场回测所有信号. sample=N 只取前N只 (调试). 返回 {signal: {N: stats}} + base_rate."""
    codes = [p.stem for p in cfg.OHLCV_DIR.glob("*.parquet")]
    if sample:
        codes = codes[:sample]
    print(f"⏳ 回测 {len(codes)} 只, {len(SIGNALS)} 信号, horizon={forward_days}")
    # 预加载 (避免每个信号重读 parquet)
    loaded = []
    for code in codes:
        d = _load_parquet(code)
        if d and len(d[0]) >= min_history + max(forward_days):
            loaded.append((code, d))
    print(f"  有效 {len(loaded)}/{len(codes)} (≥{min_history + max(forward_days)}日)")

    out = {}
    for name, fn in SIGNALS.items():
        per_stock = []
        for code, (closes, vols) in loaded:
            per_stock.append(backtest_signal(fn, closes, vols, forward_days, min_history))
        stats = aggregate_stats(per_stock, forward_days)
        out[name] = stats
        # 简报
        s5 = stats.get(5) or {}
        print(f"  {name}: n={s5.get('count', 0)} 胜率={s5.get('win_rate', 0):.1%} "
              f"5日均={s5.get('avg_return', 0):+.2%}")

    # base rate (用全样本 always-true)
    br_per = [backtest_signal(lambda c, v: True, c, v, forward_days, min_history)
              for _, (c, v) in loaded]
    br = aggregate_stats(br_per, forward_days)
    out["__base_rate__"] = br
    return out


def main():
    ap = argparse.ArgumentParser(description="历史信号回测: detector forward-return edge")
    ap.add_argument("--horizon", type=int, nargs="+", default=[5, 10, 20])
    ap.add_argument("--min-history", type=int, default=80)
    ap.add_argument("--sample", type=int, default=None, help="只取前N只 (调试)")
    args = ap.parse_args()

    fwd = tuple(args.horizon)
    out = run_all(forward_days=fwd, min_history=args.min_history, sample=args.sample)
    br = out.pop("__base_rate__")

    print(f"\n=== 历史信号回测 (base rate: "
          + ", ".join(f"{N}日均={br[N]['avg_return']:+.2%}/胜率{br[N]['win_rate']:.1%}"
                      for N in fwd if br.get(N)) + ") ===\n")
    print(f"{'信号':<22} {'horizon':>7} {'n':>7} {'胜率':>7} {'信号均值':>9} {'base':>8} {'edge':>8} {'中位':>8}")
    for name, stats in out.items():
        for N in fwd:
            s = stats.get(N)
            if not s:
                continue
            b = br.get(N) or {}
            e = edge(s["avg_return"], b.get("avg_return", 0))
            print(f"{name:<22} {N:>5}d {s['count']:>7} {s['win_rate']:>6.1%} "
                  f"{s['avg_return']:>+8.2%} {b.get('avg_return', 0):>+7.2%} "
                  f"{e:>+7.2%} {s['median']:>+7.2%}")

    # 落盘
    out_dir = cfg.DAILY_DIR / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "signal_backtest.json"
    json.dump({"signals": out, "base_rate": br,
               "horizon": list(fwd), "min_history": args.min_history,
               "run_at": date.today().isoformat()},
              open(out_file, "w"), ensure_ascii=False, indent=2)
    print(f"\n✓ 落盘 {out_file}")


if __name__ == "__main__":
    main()
