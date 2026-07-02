"""Setup Registry — edge 库 (验证过的 setup → 可 sizing 的 Kelly 分数).

把 signal_backtest 的验证结果转成仓位建议. 目标: 每个验证过的 setup 出
{win_rate, avg_win, avg_loss, payoff, expectancy, kelly_frac}, 直接连 position_sizer.

学习文档 阶段3 edge库建设: "持续验证的正期望 setup 堆出 100k".
一个 setup = 入场信号 + 止损 + horizon. 本模块给每个 setup 出 expectancy + Kelly仓位.

Kelly: f* = (p*b - q)/b, p=win_rate, q=1-p, b=payoff=avg_win/|avg_loss|.
半 Kelly 默认 (实战波动). 负期望 → 0 (不交易). 单笔封顶 30%.
"""
import argparse
from datetime import date

import a_stock.config as cfg


def expectancy(returns: list[float]) -> dict:
    """returns → {count, wins, win_rate, avg_win, avg_loss, payoff, expectancy}."""
    n = len(returns)
    if n == 0:
        return {"count": 0, "wins": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0,
                "payoff": 0, "expectancy": 0}
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    win_rate = len(wins) / n
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    payoff = avg_win / abs(avg_loss) if avg_loss < 0 else (avg_win if wins else 0)
    exp = win_rate * avg_win + (1 - win_rate) * avg_loss
    return {"count": n, "wins": len(wins), "win_rate": round(win_rate, 4),
            "avg_win": round(avg_win, 4), "avg_loss": round(avg_loss, 4),
            "payoff": round(payoff, 4), "expectancy": round(exp, 4)}


def kelly_fraction(win_rate: float, payoff: float, fraction: float = 0.5,
                   cap: float = 0.30) -> float:
    """Kelly f* = (p*b - q)/b. fraction=0.5 半Kelly. 负期望→0. 封顶cap."""
    if payoff <= 0 or win_rate <= 0:
        return 0.0
    p, q = win_rate, 1 - win_rate
    f = (p * payoff - q) / payoff
    f = max(0.0, f * fraction)
    return min(f, cap)


def _pair(fn1, fn2):
    def f(c, v):
        try:
            return bool(fn1(c, v)) and bool(fn2(c, v))
        except Exception:
            return False
    return f


def _build_setup_fns():
    """setup名 → signal_fn 映射 (供 detect_setup)."""
    from a_stock.signal_backtest import (
        signal_vcp, signal_wyckoff_accumulation, signal_wyckoff_distribution,
        signal_turtle_sys1, signal_turtle_sys2)
    return {
        "VCP突破": signal_vcp,
        "Wyckoff吸筹": signal_wyckoff_accumulation,
        "Wyckoff派发": signal_wyckoff_distribution,
        "Turtle sys1": signal_turtle_sys1,
        "Turtle sys2": signal_turtle_sys2,
        "sys1+Wyckoff吸筹": _pair(signal_turtle_sys1, signal_wyckoff_accumulation),
        "sys2+Wyckoff吸筹": _pair(signal_turtle_sys2, signal_wyckoff_accumulation),
        "sys1+VCP": _pair(signal_turtle_sys1, signal_vcp),
    }


SETUP_FNS = _build_setup_fns()


def load_registry() -> dict:
    """加载最新日期目录的 setup_registry.json → {setup_name: stats}. 无则 {}."""
    if not cfg.DAILY_DIR.exists():
        return {}
    dates = sorted(d for d in cfg.DAILY_DIR.iterdir()
                   if d.is_dir() and (d / "setup_registry.json").exists())
    if not dates:
        return {}
    import json
    try:
        data = json.loads((dates[-1] / "setup_registry.json").read_text())
        return {r["setup"]: r for r in data.get("registry", [])}
    except Exception:
        return {}


def detect_setup(code: str, registry: dict | None = None) -> str | None:
    """返回 code 当前命中的最高期望 setup (registry按expectancy降序遍历, 首命中).
    无命中/无数据 → None."""
    if registry is None:
        registry = load_registry()
    if not registry:
        return None
    import a_stock.ohlcv as ohlcv
    try:
        df = ohlcv.load_ohlcv(code)
        if len(df) < 60:
            return None
    except Exception:
        return None
    ccol = "close" if "close" in df.columns else "Close"
    vcol = "volume" if "volume" in df.columns else "Volume"
    closes = df[ccol].astype(float).tolist()
    vols = (df[vcol].astype(float).tolist() if vcol in df.columns
            else [0.0] * len(closes))
    # 按registry期望降序遍历命中的setup
    ranked = sorted(registry.items(), key=lambda kv: kv[1].get("expectancy", 0), reverse=True)
    for name, stats in ranked:
        fn = SETUP_FNS.get(name)
        if fn is None:
            continue
        try:
            if fn(closes, vols):
                return name
        except Exception:
            continue
    return None


# === setup → returns (复用 signal_backtest 全市场扫描) ===

def _collect_setup_returns(signal_fn, forward_days=(10,), min_history=80,
                           stop_pct=0.05, sample=None) -> dict:
    """对全市场跑 signal_fn, 收 forward returns (带止损). 返回 {N: [returns]}."""
    from a_stock.signal_backtest import backtest_signal, _load_parquet
    codes = [p.stem for p in cfg.OHLCV_DIR.glob("*.parquet")]
    if sample:
        codes = codes[:sample]
    per = []
    for code in codes:
        d = _load_parquet(code)
        if d and len(d[0]) >= min_history + max(forward_days):
            closes, vols, highs, lows = d
            per.append(backtest_signal(signal_fn, closes, vols, forward_days,
                                       min_history, stop_pct=stop_pct,
                                       highs=highs, lows=lows))
    merged = {N: [] for N in forward_days}
    for r in per:
        for N, rets in r.items():
            if N in merged:
                merged[N].extend(rets)
    return merged


def build_registry(stop_pct: float = 0.05, horizon: int = 10,
                   min_history: int = 80, sample=None) -> list[dict]:
    """建edge库: 验证过的setup → expectancy + Kelly. 返回registry列表 (按expectancy降序).
    setup名与 SETUP_FNS 对齐 (供 detect_setup 查找)."""
    print(f"⏳ Build registry (止损{stop_pct:.0%}, horizon={horizon}d)")
    registry = []
    for name, fn in SETUP_FNS.items():
        rets = _collect_setup_returns(fn, forward_days=(horizon,), min_history=min_history,
                                      stop_pct=stop_pct, sample=sample)[horizon]
        e = expectancy(rets)
        k = kelly_fraction(e["win_rate"], e["payoff"]) if e["count"] > 0 else 0
        registry.append({
            "setup": name, "n": e["count"], "win_rate": e["win_rate"],
            "avg_win": e["avg_win"], "avg_loss": e["avg_loss"], "payoff": e["payoff"],
            "expectancy": e["expectancy"], "kelly_frac": round(k, 3),
        })
        print(f"  {name}: n={e['count']} 胜率={e['win_rate']:.1%} "
              f"赔率={e['payoff']:.2f} 期望={e['expectancy']:+.2%} Kelly={k:.1%}")
    registry.sort(key=lambda x: x["expectancy"], reverse=True)
    return registry


def main():
    ap = argparse.ArgumentParser(description="Setup registry: 验证过的setup→Kelly仓位")
    ap.add_argument("--stop", type=float, default=5, help="止损% (默认5)")
    ap.add_argument("--horizon", type=int, default=10, help="持有期日 (默认10)")
    ap.add_argument("--sample", type=int, default=None)
    args = ap.parse_args()

    reg = build_registry(stop_pct=args.stop / 100, horizon=args.horizon, sample=args.sample)
    print(f"\n=== Setup Registry (止损{args.stop}%/{args.horizon}d) — 按期望降序 ===\n")
    print(f"{'setup':<26} {'n':>7} {'胜率':>6} {'均赢':>7} {'均亏':>7} {'赔率':>6} "
          f"{'期望/笔':>7} {'半Kelly':>7}")
    for r in reg:
        print(f"{r['setup']:<26} {r['n']:>7} {r['win_rate']:>5.1%} "
              f"{r['avg_win']:>+6.1%} {r['avg_loss']:>+6.1%} {r['payoff']:>5.2f} "
              f"{r['expectancy']:>+6.2%} {r['kelly_frac']:>6.1%}")

    out_dir = cfg.DAILY_DIR / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    import json
    out_file = out_dir / "setup_registry.json"
    json.dump({"registry": reg, "stop_pct": args.stop / 100,
               "horizon": args.horizon, "run_at": date.today().isoformat()},
              open(out_file, "w"), ensure_ascii=False, indent=2)
    print(f"\n✓ 落盘 {out_file}")


if __name__ == "__main__":
    main()
