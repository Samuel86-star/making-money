"""组合风险指标: 基于当前持仓算 Sharpe / MaxDD / Volatility / Concentration."""
import argparse
import math
import sqlite3
from datetime import date
import a_stock.config as cfg

DEFAULT_VOL_ANNUAL = {
    "etf_index": 0.20,
    "etf_sector": 0.35,
    "stock_mid":  0.45,
}
TRADING_DAYS = 244


def _classify_kind(name: str) -> str:
    n = (name or "").lower()
    if "etf" in n or "指数" in n:
        if any(k in n for k in ("50", "300", "500", "创业", "创业板", "1599", "5103", "5105")):
            return "etf_index"
        return "etf_sector"
    return "stock_mid"


def _annual_vol(code: str, name: str) -> float:
    return DEFAULT_VOL_ANNUAL[_classify_kind(name)]


def _live_price(code: str) -> float | None:
    import urllib.request, re
    prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
    try:
        with urllib.request.urlopen(f"http://qt.gtimg.cn/q={prefix}{code}", timeout=5) as r:
            data = r.read().decode("gbk", errors="ignore")
        m = re.search(r"~" + code + r"~([0-9.]+)~", data)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None


def _load_positions() -> list[dict]:
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT code, name, price, quantity
        FROM decisions
        WHERE action IN ('buy','add') AND close_date IS NULL
    """).fetchall()
    conn.close()
    agg = {}
    for r in rows:
        c = r["code"]
        if c not in agg:
            agg[c] = {"code": c, "name": r["name"] or c, "qty": 0}
        agg[c]["qty"] += r["quantity"]
    out = []
    for c, p in agg.items():
        px = _live_price(c) or 0
        out.append({**p, "price": px, "mv": px * p["qty"], "vol": _annual_vol(c, p["name"])})
    return out


def compute(positions: list[dict], cash: float = 36144.0, risk_free: float = 0.02,
            rho: float = 0.3) -> dict:
    """组合风险. 假设内部相关性 rho (A 股经验值 0.3)."""
    if not positions:
        return {"total_mv": 0, "cash": cash, "total": cash,
                "portfolio_vol_annual": 0, "sharpe": 0, "sortino": 0,
                "var_95_1d": 0, "max_dd_5d_95": 0,
                "hhi": 0, "largest_pct": 0, "n_positions": 0}

    total_stock = sum(p["mv"] for p in positions)
    total = total_stock + cash
    weights = [p["mv"] / total_stock for p in positions]
    vols = [p["vol"] for p in positions]
    n = len(positions)

    cov = [[vols[i] * vols[j] * (rho if i != j else 1) for j in range(n)] for i in range(n)]
    port_var = sum(weights[i] * weights[j] * cov[i][j] for i in range(n) for j in range(n))
    port_vol = port_var ** 0.5
    cash_weight = cash / total
    adj_vol = port_vol * (1 - cash_weight)

    sharpe = (0.0 - risk_free) / adj_vol if adj_vol else 0
    daily_vol = adj_vol / (TRADING_DAYS ** 0.5)
    var_95_1d = 1.645 * daily_vol * total
    max_dd_5d_95 = 1.645 * daily_vol * total * (5 ** 0.5) * 1.5
    hhi = sum(w ** 2 for w in weights)
    largest = max(weights)

    return {
        "total_mv": round(total_stock),
        "cash": round(cash),
        "total": round(total),
        "n_positions": n,
        "portfolio_vol_annual": round(adj_vol, 4),
        "daily_vol": round(daily_vol, 4),
        "sharpe": round(sharpe, 2),
        "sortino": round(sharpe, 2),  # FIXME: 暂用 Sharpe 替代, 需真实现下行波动率
        "var_95_1d": round(var_95_1d),
        "var_95_1d_pct": round(var_95_1d / total * 100, 2),
        "max_dd_5d_95": round(max_dd_5d_95),
        "max_dd_5d_95_pct": round(max_dd_5d_95 / total * 100, 2),
        "hhi": round(hhi, 4),
        "largest_pct": round(largest * 100, 2),
        "positions": [
            {"code": p["code"], "name": p["name"][:10],
             "weight": round(p["mv"] / total * 100, 2),
             "vol": p["vol"], "mv": round(p["mv"])}
            for p in positions
        ],
    }


def _bar(label: str, val: float, max_val: float, width: int = 20) -> str:
    if max_val <= 0:
        return f"  {label:<14}  -"
    filled = int(min(val / max_val, 1.0) * width)
    return f"  {label:<14}  {'█' * filled}{' ' * (width - filled)}  {val:>6.2f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cash", type=float, default=36144.0)
    ap.add_argument("--rf", type=float, default=0.02)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    positions = _load_positions()
    r = compute(positions, args.cash, args.rf)

    print(f"=== 组合风险报告 ({date.today()}) ===\n")
    print(f"股票市值:   {r['total_mv']:>10,} 元 ({len(positions)} 只)")
    print(f"现金:       {r['cash']:>10,} 元")
    print(f"总资产:     {r['total']:>10,} 元\n")
    print(f"组合年化波动率:  {r['portfolio_vol_annual']:.1%}")
    print(f"日波动率:        {r['daily_vol']:.2%}")
    print(f"Sharpe (μ=0):    {r['sharpe']:.2f}")
    print(f"Sortino:         {r['sortino']:.2f}")
    print(f"1d VaR 95%:      {r['var_95_1d']:>6,} 元 ({r['var_95_1d_pct']:.2f}%)")
    print(f"5d MaxDD 95%:    {r['max_dd_5d_95']:>6,} 元 ({r['max_dd_5d_95_pct']:.2f}%)")
    print(f"HHI 集中度:      {r['hhi']:.4f}  (1/N={1/max(r['n_positions'],1):.4f})")
    print(f"最大单仓占比:    {r['largest_pct']:.1f}%\n")
    print("持仓权重:")
    if r["positions"]:
        max_w = max(p["weight"] for p in r["positions"])
        for p in r["positions"]:
            print(_bar(p["code"], p["weight"], max_w))

    print("\n=== 风险提示 ===")
    warnings = []
    if r["largest_pct"] > 30:
        warnings.append(f"  ⚠️  最大仓 {r['largest_pct']:.0f}% > 30%, 集中度风险")
    if r["hhi"] > 0.3:
        warnings.append(f"  ⚠️  HHI {r['hhi']:.2f} > 0.3, 集中度高")
    if r["var_95_1d_pct"] > 3:
        warnings.append(f"  ⚠️  1d VaR {r['var_95_1d_pct']:.1f}% 较大, 注意日内回撤")
    if r["n_positions"] < 4:
        warnings.append(f"  ⚠️  持仓仅 {r['n_positions']} 只, 分散不足")
    if not warnings:
        warnings.append("  ✅ 当前风险在可控范围")
    print("\n".join(warnings))

    if args.json:
        import json
        print()
        print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
