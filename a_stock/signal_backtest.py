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
                    min_history: int = 60,
                    stop_pct: float | None = None,
                    highs: list | None = None, lows: list | None = None) -> dict:
    """单股滑动回测. 对每个 T (min_history ≤ T < n-max_N), 跑 signal_fn(closes[:T+1], vols[:T+1]).
    命中 (返回真值) 则记 forward return.

    stop_pct=None: forward return = (close[T+N]-close[T])/close[T] (满horizon不止损).
    stop_pct=0.03: 任意日 T+1..T+N 的 low ≤ entry×(1-3%) → 止损出场 return=-3%;
                   否则持有到 close[T+N]. 需 highs/lows, 缺则回退无止损模式.

    返回 {N: [returns]} 原始列表. signal_fn 异常当未命中."""
    use_stop = stop_pct is not None and highs and lows
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
        if entry <= 0:
            continue
        for N in forward_days:
            if use_stop:
                h_fwd = highs[T + 1:T + 1 + N]
                l_fwd = lows[T + 1:T + 1 + N]
                c_fwd = closes[T + 1:T + 1 + N]
                ret = realized_return_with_stop(entry, h_fwd, l_fwd, c_fwd, stop_pct, N)
                if ret is not None:
                    results[N].append(ret)
            elif T + N < n:
                results[N].append((closes[T + N] - entry) / entry)
    return results


def realized_return_with_stop(entry: float, highs_fwd: list, lows_fwd: list,
                              closes_fwd: list, stop_pct: float, N: int) -> float | None:
    """带止损的forward收益. *_fwd = T+1..T+N 的 High/Low/Close.
    任意日 low ≤ entry×(1-stop_pct) → 止损, return=-stop_pct (用low判, 日内触发).
    否则 return = (closes_fwd[N-1]-entry)/entry. 数据不足N日返回None."""
    if entry <= 0 or N <= 0:
        return None
    if len(lows_fwd) < N or len(closes_fwd) < N:
        return None
    stop_price = entry * (1 - stop_pct)
    for i in range(N):
        if lows_fwd[i] <= stop_price:
            return -stop_pct  # 止损出场 (保守: 按stop价, 不按实际low)
    return (closes_fwd[N - 1] - entry) / entry


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


# === 信号 confluence (多信号同日触发) ===

def confluence_backtest(signal_fns: list, closes: list, vols: list,
                        highs: list | None = None, lows: list | None = None,
                        forward_days: tuple = (5, 10, 20),
                        min_history: int = 60,
                        stop_pct: float | None = None) -> dict:
    """单股: 每T数信号命中数, 按count分桶记forward return.
    返回 {count: {N: [returns]}}. count=0跳过. 信号异常当未fire."""
    use_stop = stop_pct is not None and highs and lows
    buckets = {}
    n = len(closes)
    max_N = max(forward_days)
    for T in range(min_history, n - max_N):
        count = 0
        for fn in signal_fns:
            try:
                if fn(closes[:T + 1], vols[:T + 1]):
                    count += 1
            except Exception:
                pass
        if count == 0:
            continue
        entry = closes[T]
        if entry <= 0:
            continue
        buckets.setdefault(count, {N: [] for N in forward_days})
        for N in forward_days:
            if use_stop:
                ret = realized_return_with_stop(entry, highs[T + 1:T + 1 + N],
                                                lows[T + 1:T + 1 + N],
                                                closes[T + 1:T + 1 + N], stop_pct, N)
            elif T + N < n:
                ret = (closes[T + N] - entry) / entry
            else:
                ret = None
            if ret is not None:
                buckets[count][N].append(ret)
    return buckets


def aggregate_confluence(per_stock_buckets: list, forward_days: tuple) -> dict:
    """合并多股 confluence 桶. count≥3 折叠到 '3' (标3+).
    返回 {count: {N: stats}}."""
    merged = {}
    for b in per_stock_buckets:
        for count, ndict in b.items():
            key = count if count <= 2 else 3  # 折叠3+
            merged.setdefault(key, {N: [] for N in forward_days})
            for N, rets in ndict.items():
                if N in merged[key]:
                    merged[key][N].extend(rets)
    return {k: aggregate_stats([{N: v for N, v in ndict.items()}], forward_days)
            for k, ndict in merged.items()}


# === 2信号子组合拆解 (哪对组合是confluence的edge来源) ===

def backtest_pairs(signal_fns: list, signal_names: list, closes: list, vols: list,
                   highs: list | None = None, lows: list | None = None,
                   forward_days: tuple = (5, 10, 20),
                   min_history: int = 60, stop_pct: float | None = None) -> dict:
    """每T, 对所有fire的2-信号组合 (C(n,2)), 按pair记forward return.
    pair_key = '+'.join(sorted([name_i, name_j])). 返回 {pair_key: {N: [returns]}}."""
    from itertools import combinations
    use_stop = stop_pct is not None and highs and lows
    pairs: dict = {}
    n = len(closes)
    max_N = max(forward_days)
    for T in range(min_history, n - max_N):
        fired_idx = []
        for i, fn in enumerate(signal_fns):
            try:
                if fn(closes[:T + 1], vols[:T + 1]):
                    fired_idx.append(i)
            except Exception:
                pass
        if len(fired_idx) < 2:
            continue
        entry = closes[T]
        if entry <= 0:
            continue
        for i, j in combinations(fired_idx, 2):
            key = "+".join(sorted([signal_names[i], signal_names[j]]))
            pairs.setdefault(key, {N: [] for N in forward_days})
            for N in forward_days:
                if use_stop:
                    ret = realized_return_with_stop(entry, highs[T + 1:T + 1 + N],
                                                    lows[T + 1:T + 1 + N],
                                                    closes[T + 1:T + 1 + N], stop_pct, N)
                elif T + N < n:
                    ret = (closes[T + N] - entry) / entry
                else:
                    ret = None
                if ret is not None:
                    pairs[key][N].append(ret)
    return pairs


def aggregate_pairs(per_stock_pairs: list, forward_days: tuple) -> dict:
    """合并多股 pair → {pair_key: {N: stats}}."""
    merged: dict = {}
    for p in per_stock_pairs:
        for key, ndict in p.items():
            merged.setdefault(key, {N: [] for N in forward_days})
            for N, rets in ndict.items():
                if N in merged[key]:
                    merged[key][N].extend(rets)
    return {k: aggregate_stats([{N: v for N, v in ndict.items()}], forward_days)
            for k, ndict in merged.items()}


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


# === 信号变体 (2026-07: refinement研究) ===

def signal_turtle_sys2_vol(closes, vols):
    """sys2突破 + 当日量≥1.5×20日均 (volume确认). 研究: 量能过滤能否提升低胜率sys2."""
    from a_stock.turtle import breakout_signal
    if breakout_signal(closes) != "sys2_breakout":
        return False
    if len(vols) < 21:
        return False
    avg = sum(vols[-21:-1]) / 20
    return avg > 0 and vols[-1] >= avg * 1.5


def signal_wyckoff_spring(closes, vols):
    """Wyckoff Spring only (假跌破+回升), 不含 vol_asymmetry. 研究: Spring是否比含vol_asym的吸筹edge更高."""
    from a_stock.scorers.technical_scorer import _detect_wyckoff
    w = _detect_wyckoff(closes, vols)
    return w is not None and w["phase"] == "accumulation" and w["signal"] == "Spring"


def signal_wyckoff_accum_strict(closes, vols):
    """Wyckoff吸筹严版: Spring (本身强) OR vol_asymmetry ratio≤0.5 (严于默认0.67)."""
    from a_stock.scorers.technical_scorer import _detect_wyckoff
    w = _detect_wyckoff(closes, vols)
    if not w or w["phase"] != "accumulation":
        return False
    if w["signal"] == "Spring":
        return True
    return w.get("vol_ratio", 1.0) <= 0.5


SIGNALS = {
    "VCP(Minervini)": signal_vcp,
    "Wyckoff吸筹": signal_wyckoff_accumulation,
    "Wyckoff派发": signal_wyckoff_distribution,
    "Turtle sys1(20日突破)": signal_turtle_sys1,
    "Turtle sys2(55日突破)": signal_turtle_sys2,
}

VARIANTS = {
    "Turtle sys2+量确认": signal_turtle_sys2_vol,
    "Wyckoff Spring-only": signal_wyckoff_spring,
    "Wyckoff吸筹(严)": signal_wyckoff_accum_strict,
}


def _load_parquet(code: str):
    """加载单只 parquet → (closes, vols, highs, lows). 失败返回 None."""
    f = cfg.OHLCV_DIR / f"{code}.parquet"
    if not f.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(f)
        def _col(*names):
            for nm in names:
                if nm in df.columns:
                    return df[nm].astype(float).tolist()
            return []
        closes = _col("close", "Close")
        vols = _col("volume", "Volume") or [0.0] * len(closes)
        highs = _col("high", "High")
        lows = _col("low", "Low")
        return closes, vols, highs, lows
    except Exception:
        return None


def run_all(forward_days=(5, 10, 20), min_history=80, sample=None,
            stop_pct=None) -> dict:
    """全市场回测所有信号. stop_pct=0.03 启用止损建模 (需High/Low).
    返回 {signal: {N: stats}} + base_rate."""
    codes = [p.stem for p in cfg.OHLCV_DIR.glob("*.parquet")]
    if sample:
        codes = codes[:sample]
    mode = f"止损{stop_pct:.0%}" if stop_pct else "无止损(满horizon)"
    print(f"⏳ 回测 {len(codes)} 只, {len(SIGNALS)} 信号, horizon={forward_days}, {mode}")
    loaded = []
    for code in codes:
        d = _load_parquet(code)
        if d and len(d[0]) >= min_history + max(forward_days):
            loaded.append((code, d))
    print(f"  有效 {len(loaded)}/{len(codes)} (≥{min_history + max(forward_days)}日)")

    out = {}
    for name, fn in SIGNALS.items():
        per_stock = []
        for code, (closes, vols, highs, lows) in loaded:
            per_stock.append(backtest_signal(fn, closes, vols, forward_days, min_history,
                                             stop_pct=stop_pct, highs=highs, lows=lows))
        stats = aggregate_stats(per_stock, forward_days)
        out[name] = stats
        s5 = stats.get(5) or {}
        print(f"  {name}: n={s5.get('count', 0)} 胜率={s5.get('win_rate', 0):.1%} "
              f"5日均={s5.get('avg_return', 0):+.2%}")

    # base rate (always-true, 同stop模式)
    br_per = [backtest_signal(lambda c, v: True, c, v, forward_days, min_history,
                              stop_pct=stop_pct, highs=h, lows=lw)
              for _, (c, v, h, lw) in loaded]
    br = aggregate_stats(br_per, forward_days)
    out["__base_rate__"] = br
    return out


def run_confluence(forward_days=(5, 10, 20), min_history=80, sample=None,
                   stop_pct=None) -> dict:
    """全市场 confluence 回测. 返回 {count_bucket: {N: stats}} + base_rate."""
    codes = [p.stem for p in cfg.OHLCV_DIR.glob("*.parquet")]
    if sample:
        codes = codes[:sample]
    sig_fns = list(SIGNALS.values())
    mode = f"止损{stop_pct:.0%}" if stop_pct else "无止损"
    print(f"⏳ Confluence 回测 {len(codes)} 只, {len(sig_fns)}信号, horizon={forward_days}, {mode}")
    loaded = []
    for code in codes:
        d = _load_parquet(code)
        if d and len(d[0]) >= min_history + max(forward_days):
            loaded.append(d)
    print(f"  有效 {len(loaded)}/{len(codes)}")

    per = []
    for closes, vols, highs, lows in loaded:
        per.append(confluence_backtest(sig_fns, closes, vols, highs, lows,
                                       forward_days, min_history, stop_pct))
    buckets = aggregate_confluence(per, forward_days)

    # base rate (always-true, 同stop模式)
    br_per = [backtest_signal(lambda c, v: True, c, v, forward_days, min_history,
                              stop_pct=stop_pct, highs=h, lows=lw)
              for c, v, h, lw in loaded]
    br = aggregate_stats(br_per, forward_days)
    return buckets, br


def run_pairs(forward_days=(5, 10, 20), min_history=80, sample=None,
              stop_pct=None) -> tuple:
    """全市场2信号子组合拆解. 返回 ({pair_key: {N: stats}}, base_rate)."""
    codes = [p.stem for p in cfg.OHLCV_DIR.glob("*.parquet")]
    if sample:
        codes = codes[:sample]
    names = list(SIGNALS.keys())
    fns = list(SIGNALS.values())
    mode = f"止损{stop_pct:.0%}" if stop_pct else "无止损"
    print(f"⏳ Pairs 回测 {len(codes)} 只, {len(fns)}信号两两组合, {mode}")
    loaded = []
    for code in codes:
        d = _load_parquet(code)
        if d and len(d[0]) >= min_history + max(forward_days):
            loaded.append(d)
    print(f"  有效 {len(loaded)}/{len(codes)}")
    per = [backtest_pairs(fns, names, c, v, h, lw, forward_days, min_history, stop_pct)
           for c, v, h, lw in loaded]
    pairs = aggregate_pairs(per, forward_days)
    br_per = [backtest_signal(lambda x, y: True, c, v, forward_days, min_history,
                              stop_pct=stop_pct, highs=h, lows=lw)
              for c, v, h, lw in loaded]
    br = aggregate_stats(br_per, forward_days)
    return pairs, br


def run_variants(forward_days=(5, 10, 20), min_history=80, sample=None,
                 stop_pct=None) -> tuple:
    """全市场变体对比 (VARIANTS + 原版). 返回 ({name: {N: stats}}, base_rate)."""
    codes = [p.stem for p in cfg.OHLCV_DIR.glob("*.parquet")]
    if sample:
        codes = codes[:sample]
    both = {**SIGNALS, **VARIANTS}
    mode = f"止损{stop_pct:.0%}" if stop_pct else "无止损"
    print(f"⏳ Variants 回测 {len(codes)} 只, {len(both)}信号(原+变体), {mode}")
    loaded = []
    for code in codes:
        d = _load_parquet(code)
        if d and len(d[0]) >= min_history + max(forward_days):
            loaded.append(d)
    print(f"  有效 {len(loaded)}/{len(codes)}")
    out = {}
    for name, fn in both.items():
        per = [backtest_signal(fn, c, v, forward_days, min_history,
                               stop_pct=stop_pct, highs=h, lows=lw)
               for c, v, h, lw in loaded]
        out[name] = aggregate_stats(per, forward_days)
    br_per = [backtest_signal(lambda x, y: True, c, v, forward_days, min_history,
                              stop_pct=stop_pct, highs=h, lows=lw)
              for c, v, h, lw in loaded]
    br = aggregate_stats(br_per, forward_days)
    return out, br


def main():
    ap = argparse.ArgumentParser(description="历史信号回测: detector forward-return edge")
    ap.add_argument("--horizon", type=int, nargs="+", default=[5, 10, 20])
    ap.add_argument("--min-history", type=int, default=80)
    ap.add_argument("--sample", type=int, default=None, help="只取前N只 (调试)")
    ap.add_argument("--stop", type=float, default=None, help="止损% (如3=3%%), 启用止损建模")
    ap.add_argument("--confluence", action="store_true", help="多信号叠加模式")
    ap.add_argument("--pairs", action="store_true", help="2信号子组合拆解")
    ap.add_argument("--variants", action="store_true", help="信号变体对比(sys2+量/Wyckoff严)")
    args = ap.parse_args()

    fwd = tuple(args.horizon)
    stop = args.stop / 100 if args.stop else None

    if args.pairs:
        pairs, br = run_pairs(fwd, args.min_history, args.sample, stop)
        mode = f"pairs[{f'止损{args.stop}%' if stop else '无止损'}]"
        print(f"\n=== 2信号子组合 [{mode}] (base: "
              + ", ".join(f"{N}日均={br[N]['avg_return']:+.2%}" for N in fwd if br.get(N)) + ") ===\n")
        rows = []
        for pair, stats in pairs.items():
            s = stats.get(fwd[1]) if len(fwd) > 1 else stats.get(fwd[0])
            if not s:
                continue
            b = br.get(fwd[1] if len(fwd) > 1 else fwd[0]) or {}
            rows.append((pair, s, edge(s["avg_return"], b.get("avg_return", 0))))
        rows.sort(key=lambda r: r[2], reverse=True)
        print(f"{'信号对':<32} {'n':>7} {'胜率':>7} {'均值':>8} {'edge':>8} {'中位':>8}")
        for pair, s, e in rows:
            print(f"{pair:<32} {s['count']:>7} {s['win_rate']:>6.1%} "
                  f"{s['avg_return']:>+7.2%} {e:>+7.2%} {s['median']:>+7.2%}")
        out_dir = cfg.DAILY_DIR / date.today().isoformat()
        out_dir.mkdir(parents=True, exist_ok=True)
        tag = f"_stop{args.stop}" if stop else ""
        json.dump({"pairs": {k: v for k, v in pairs.items()}, "base_rate": br,
                   "stop_pct": stop, "run_at": date.today().isoformat()},
                  open(out_dir / f"pairs{tag}.json", "w"), ensure_ascii=False, indent=2)
        print(f"\n✓ 落盘 {out_dir / f'pairs{tag}.json'}")
        return

    if args.variants:
        out, br = run_variants(fwd, args.min_history, args.sample, stop)
        mode = f"variants[{f'止损{args.stop}%' if stop else '无止损'}]"
        print(f"\n=== 信号变体对比 [{mode}] (base: "
              + ", ".join(f"{N}日均={br[N]['avg_return']:+.2%}" for N in fwd if br.get(N)) + ") ===\n")
        N = fwd[1] if len(fwd) > 1 else fwd[0]
        print(f"{'信号':<26} {'n':>8} {'胜率':>7} {'均值':>8} {'base':>8} {'edge':>8} {'中位':>8}")
        for name, stats in out.items():
            s = stats.get(N)
            if not s:
                continue
            b = br.get(N) or {}
            e = edge(s["avg_return"], b.get("avg_return", 0))
            print(f"{name:<26} {s['count']:>8} {s['win_rate']:>6.1%} "
                  f"{s['avg_return']:>+7.2%} {b.get('avg_return',0):>+7.2%} {e:>+7.2%} {s['median']:>+7.2%}")
        return

    if args.confluence:
        buckets, br = run_confluence(fwd, args.min_history, args.sample, stop)
        mode = f"confluence[{f'止损{args.stop}%' if stop else '无止损'}]"
        print(f"\n=== Confluence 回测 [{mode}] (base: "
              + ", ".join(f"{N}日均={br[N]['avg_return']:+.2%}" for N in fwd if br.get(N))
              + ") ===\n")
        print(f"{'叠加数':<8} {'horizon':>7} {'n':>8} {'胜率':>7} {'均值':>8} {'base':>8} {'edge':>8} {'中位':>8}")
        for count in sorted(buckets.keys()):
            label = f"{count}信号" if count < 3 else "3+信号"
            for N in fwd:
                s = buckets[count].get(N)
                if not s:
                    continue
                b = br.get(N) or {}
                e = edge(s["avg_return"], b.get("avg_return", 0))
                print(f"{label:<8} {N:>5}d {s['count']:>8} {s['win_rate']:>6.1%} "
                      f"{s['avg_return']:>+7.2%} {b.get('avg_return', 0):>+7.2%} "
                      f"{e:>+7.2%} {s['median']:>+7.2%}")
        out_dir = cfg.DAILY_DIR / date.today().isoformat()
        out_dir.mkdir(parents=True, exist_ok=True)
        tag = f"_stop{args.stop}" if stop else ""
        out_file = out_dir / f"confluence{tag}.json"
        json.dump({"buckets": {str(k): v for k, v in buckets.items()},
                   "base_rate": br, "mode": mode, "stop_pct": stop,
                   "horizon": list(fwd), "run_at": date.today().isoformat()},
                  open(out_file, "w"), ensure_ascii=False, indent=2)
        print(f"\n✓ 落盘 {out_file}")
        return

    out = run_all(forward_days=fwd, min_history=args.min_history, sample=args.sample,
                  stop_pct=stop)
    br = out.pop("__base_rate__")

    mode = f"止损{args.stop}%" if stop else "无止损"
    print(f"\n=== 历史信号回测 [{mode}] (base rate: "
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

    out_dir = cfg.DAILY_DIR / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"_stop{args.stop}" if stop else ""
    out_file = out_dir / f"signal_backtest{tag}.json"
    json.dump({"signals": out, "base_rate": br, "mode": mode,
               "horizon": list(fwd), "min_history": args.min_history,
               "stop_pct": stop, "run_at": date.today().isoformat()},
              open(out_file, "w"), ensure_ascii=False, indent=2)
    print(f"\n✓ 落盘 {out_file}")


if __name__ == "__main__":
    main()
