"""仓位计算器: 凯利公式 + 固定比例 + 波动率倒数加权."""
import argparse
from dataclasses import dataclass


@dataclass
class Candidate:
    code: str
    name: str
    price: float
    target_price: float
    stop_loss: float
    vol_annual: float = 0.30
    win_rate: float = 0.5


def _fractional_kelly(win_rate: float, payoff_ratio: float, fraction: float = 0.5) -> float:
    """f* = (p*b - q) / b, 半凯利默认."""
    if payoff_ratio <= 0:
        return 0.0
    p, q = win_rate, 1 - win_rate
    f = (p * payoff_ratio - q) / payoff_ratio
    return max(0, f * fraction)


def _fixed_fractional(risk_per_trade: float, stop_distance_pct: float) -> float:
    if stop_distance_pct <= 0:
        return 0.0
    return risk_per_trade / stop_distance_pct


def _vol_weighted(positions_vols: list[float]) -> list[float]:
    if not positions_vols or any(v <= 0 for v in positions_vols):
        return [1.0 / len(positions_vols)] * len(positions_vols) if positions_vols else []
    inv = [1.0 / v for v in positions_vols]
    s = sum(inv)
    return [x / s for x in inv]


def suggest(c: Candidate, total_capital: float, method: str = "kelly",
            risk_per_trade: float = 0.01, kelly_fraction: float = 0.5,
            score: float | None = None, setup: str | None = None,
            registry: dict | None = None) -> dict:
    stop_pct = (c.price - c.stop_loss) / c.price
    target_pct = (c.target_price - c.price) / c.price
    payoff = target_pct / stop_pct if stop_pct > 0 else 0
    # Van Tharp R 倍数: 1R = 每股风险, reward = 每股目标收益
    risk_per_share = c.price - c.stop_loss
    reward_per_share = c.target_price - c.price
    r_multiple = reward_per_share / risk_per_share if risk_per_share > 0 else 0

    # 凯利用的 win_rate/payoff: setup backtested 优先 (验证驱动sizing)
    eff_win_rate = c.win_rate
    eff_payoff = payoff
    setup_note = ""
    if setup:
        if registry is None:
            from a_stock.setup_registry import load_registry
            registry = load_registry()
        entry = registry.get(setup)
        if entry:
            eff_win_rate = entry.get("win_rate", c.win_rate)
            eff_payoff = entry.get("payoff", payoff)
            setup_note = (f" [setup={setup} 回测w{eff_win_rate:.0%}/b{eff_payoff:.2f} "
                          f"E{entry.get('expectancy', 0):+.2%}]")

    if method == "kelly":
        frac = _fractional_kelly(eff_win_rate, eff_payoff, kelly_fraction)
        rationale = f"Kelly({eff_win_rate:.0%}×{eff_payoff:.2f})×{kelly_fraction}={frac:.1%}{setup_note}"
    elif method == "fixed":
        frac = _fixed_fractional(risk_per_trade, stop_pct)
        rationale = f"固定风险 风险1R={risk_per_trade:.1%}资本/止损{stop_pct:.1%} 博{r_multiple:.1f}R{setup_note}"
    else:
        frac = 0.10
        rationale = "vol 不适用单标的"

    # Phase3: 多因子评分缩放仓位 (<40→0 / 40-60→半 / 60-80→满 / >=80→超配)
    scale = 1.0
    if score is not None:
        from a_stock.scorers import score_to_position_scale
        scale = score_to_position_scale(score)
        frac = frac * scale
        rationale += f" ×评分{score:.0f}(×{scale})"

    frac = min(frac, 0.30)
    amount = total_capital * frac
    shares = max(int(amount / c.price / 100) * 100, 0)
    actual_amount = shares * c.price
    actual_pct = actual_amount / total_capital if total_capital else 0

    return {
        "code": c.code, "name": c.name, "method": method,
        "rationale": rationale,
        "score": score, "setup": setup,
        "suggested_frac": round(frac, 4),
        "suggested_amount": round(amount),
        "shares": shares,
        "actual_amount": round(actual_amount),
        "actual_pct": round(actual_pct, 4),
        "stop_pct": round(stop_pct, 4),
        "target_pct": round(target_pct, 4),
        "payoff_ratio": round(payoff, 2),
        "risk_per_share": round(risk_per_share, 4),
        "reward_per_share": round(reward_per_share, 4),
        "R_multiple": round(r_multiple, 2),
        "backtested_win_rate": round(eff_win_rate, 4) if setup else None,
        "backtested_payoff": round(eff_payoff, 2) if setup else None,
    }


def portfolio_vol_weight(positions: list[Candidate]) -> list[dict]:
    vols = [p.vol_annual for p in positions]
    weights = _vol_weighted(vols)
    return [
        {"code": p.code, "name": p.name,
         "weight": round(w, 4), "vol": p.vol_annual,
         "contrib_vol": round(w * p.vol_annual, 4)}
        for p, w in zip(positions, weights)
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", choices=["kelly", "fixed", "vol"], default="kelly")
    ap.add_argument("--capital", type=float, default=78788.0)
    ap.add_argument("--risk", type=float, default=0.01)
    ap.add_argument("--win-rate", type=float, default=0.55)
    ap.add_argument("--kelly-frac", type=float, default=0.5)
    args = ap.parse_args()

    candidates = [
        Candidate("515650", "消费50ETF",    0.955, 1.05, 0.90, vol_annual=0.20, win_rate=0.55),
        Candidate("600276", "恒瑞医药",     48.67, 55.0, 45.0, vol_annual=0.45, win_rate=0.60),
        Candidate("300059", "东方财富",     20.07, 24.0, 18.0, vol_annual=0.50, win_rate=0.50),
        Candidate("159801", "芯片ETF广发",  1.547, 1.85, 1.40, vol_annual=0.40, win_rate=0.50),
        Candidate("159915", "创业板ETF",    4.215, 4.80, 3.80, vol_annual=0.25, win_rate=0.60),
        Candidate("515880", "通信ETF",      1.757, 1.95, 1.50, vol_annual=0.40, win_rate=0.45),
    ]

    print(f"=== 仓位建议 (资金 {args.capital:,.0f}, 方法={args.method}) ===\n")
    print(f"{'代码':<8} {'名称':<14} {'建议占比':<10} {'建议金额':<12} {'股数':<8} {'实际%':<8} {'理由'}")
    for c in candidates:
        r = suggest(c, args.capital, args.method, args.risk, args.kelly_frac)
        print(f"{r['code']:<8} {r['name']:<14} {r['suggested_frac']:>6.1%}    "
              f"{r['suggested_amount']:>10,}   {r['shares']:>6}   {r['actual_pct']:>6.1%}   "
              f"{r['rationale']}")

    if args.method == "vol":
        print("\n--- 多标的波动率倒数加权 ---")
        weights = portfolio_vol_weight(candidates)
        for w in weights:
            print(f"  {w['code']:<8} 权重 {w['weight']:.1%}  vol {w['vol']:.0%}  贡献 {w['contrib_vol']:.1%}")


if __name__ == "__main__":
    main()
