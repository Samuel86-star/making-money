"""Edge Scanner — 验证edge → 今天买什么.

扫全市场parquet, 找当前命中验证setup的股, 按setup期望排序, 出actionable建议:
代码/setup/现价/止损/目标/股数/半Kelly. 连 position_sizer (backtested参数).
成本扣减: 默认round-trip 0.3% (佣金+印花税+滑点), 净期望≤0的setup滤除.

闭环: setup_registry(验证) → detect_setup(命中) → position_sizer(sizing) → 候选清单.
"""
import argparse
from datetime import date

import a_stock.config as cfg
from a_stock.setup_registry import load_registry, detect_setup
from a_stock.position_sizer import Candidate, suggest


def _stock_name(code: str) -> str:
    """从parquet或db取名, 失败返回code."""
    try:
        import sqlite3
        db = sqlite3.connect("data/decisions.sqlite")
        r = db.execute("SELECT name FROM decisions WHERE code=? LIMIT 1", (code,)).fetchone()
        db.close()
        if r:
            return r[0]
    except Exception:
        pass
    return code


def scan_for_setups(capital: float = 79938.0, stop_pct: float = 0.05,
                    cost_pct: float = 0.003, top_n: int = 20,
                    min_expectancy: float | None = None) -> list[dict]:
    """扫全市场, 找当前命中验证setup的股, 出actionable sized建议.

    stop_pct: 止损% (默认5, 回测甜区). cost_pct: round-trip成本 (默认0.3%).
    min_expectancy: 净期望下限 (默认=cost_pct, 即净期望>0才推). 返回top_n."""
    registry = load_registry()
    if not registry:
        print("⚠ registry空, 先跑 `python -m a_stock.setup_registry`")
        return []
    if min_expectancy is None:
        min_expectancy = cost_pct  # 净期望>0才值得 (覆盖成本)

    codes = [p.stem for p in cfg.OHLCV_DIR.glob("*.parquet")]
    recs = []
    import pandas as pd
    for code in codes:
        try:
            setup = detect_setup(code, registry)
            if not setup:
                continue
            stats = registry[setup]
            # 净期望 (扣成本)
            net_exp = stats.get("expectancy", 0) - cost_pct
            if net_exp <= 0:
                continue  # 成本吃光edge, 不推
            df = pd.read_parquet(cfg.OHLCV_DIR / f"{code}.parquet")
            ccol = "close" if "close" in df.columns else "Close"
            price = float(df[ccol].iloc[-1])
            if price <= 0:
                continue
            stop = price * (1 - stop_pct)
            target = price * (1 + stats.get("payoff", 1.5) * stop_pct)
            c = Candidate(code, _stock_name(code), price, target, stop,
                          vol_annual=0.4, win_rate=stats.get("win_rate", 0.5))
            r = suggest(c, capital, method="kelly", kelly_fraction=0.5,
                        setup=setup, registry=registry)
            r["entry"] = round(price, 3)
            r["stop"] = round(stop, 3)
            r["target"] = round(target, 3)
            r["net_expectancy"] = round(net_exp, 4)
            r["kelly_frac"] = stats.get("kelly_frac", 0)
            r["setup"] = setup
            recs.append(r)
        except Exception:
            continue
    recs.sort(key=lambda r: (registry[r["setup"]].get("expectancy", 0),
                             r.get("net_expectancy", 0)), reverse=True)
    return recs[:top_n]


def main():
    ap = argparse.ArgumentParser(description="Edge scanner: 验证setup → 今天买什么")
    ap.add_argument("--capital", type=float, default=79938.0)
    ap.add_argument("--stop", type=float, default=5, help="止损% (默认5甜区)")
    ap.add_argument("--cost", type=float, default=0.3, help="round-trip成本% (默认0.3)")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    recs = scan_for_setups(capital=args.capital, stop_pct=args.stop / 100,
                           cost_pct=args.cost / 100, top_n=args.top)
    if not recs:
        print("无候选 (当前无setup命中, 或净期望≤成本). 先跑 setup_registry.")
        return

    print(f"\n=== Edge Scanner 候选 (资本{args.capital:,.0f}/止损{args.stop}%/成本{args.cost}%) ===\n")
    print(f"{'代码':<8} {'名称':<10} {'setup':<20} {'现价':>7} {'止损':>7} {'目标':>7} "
          f"{'股数':>6} {'占比':>5} {'净期望':>6}")
    for r in recs:
        print(f"{r['code']:<8} {r['name'][:10]:<10} {r['setup']:<20} "
              f"{r['entry']:>7.3f} {r['stop']:>7.3f} {r['target']:>7.3f} "
              f"{r['shares']:>6} {r['actual_pct']:>4.1%} {r['net_expectancy']:>+5.2%}")

    out_dir = cfg.DAILY_DIR / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    import json
    out_file = out_dir / "edge_scanner.json"
    json.dump({"candidates": [{k: v for k, v in r.items()} for r in recs],
               "capital": args.capital, "stop_pct": args.stop / 100,
               "cost_pct": args.cost / 100, "run_at": date.today().isoformat()},
              open(out_file, "w"), ensure_ascii=False, indent=2, default=str)
    print(f"\n✓ 落盘 {out_file}")


if __name__ == "__main__":
    main()
