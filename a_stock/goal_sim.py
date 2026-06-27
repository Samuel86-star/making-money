"""蒙特卡洛目标概率: 给定当前组合, 模拟 N 条路径, 算 P(达目标)."""
import argparse
import json
import sqlite3
import random
from datetime import date, datetime
from pathlib import Path
import a_stock.config as cfg

# 历史波动率参考(年化, 用于校准)
# 保守起见用 max(各持仓隐含波动, 行业基准)
DEFAULT_VOL_ANNUAL = {
    "etf_index": 0.20,      # 宽基 ETF
    "etf_sector": 0.35,     # 行业 ETF (芯片/通信/消费)
    "stock_mid":  0.45,     # 中线个股
}

# 现金年化 1.5%
CASH_RATE = 0.015

# 模拟次数
N_SIMS = 10000

# 交易日/年
TRADING_DAYS = 244


def _classify_kind(name: str) -> str:
    """根据代码/名称判断类型, 用于取波动率。"""
    n = (name or "").lower()
    if "etf" in n or "指数" in n:
        if any(k in n for k in ("50", "300", "500", "创业", "创业板", "1599", "5103", "5105")):
            return "etf_index"
        return "etf_sector"
    return "stock_mid"


def _annual_vol(code: str, name: str) -> float:
    return DEFAULT_VOL_ANNUAL[_classify_kind(name)]


def _load_positions() -> list[dict]:
    """从 decisions.sqlite 读当前 open 持仓 + DB 里登记的均价."""
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT code, name, price, quantity
        FROM decisions
        WHERE action IN ('buy','add') AND close_date IS NULL
    """).fetchall()
    # 同 code 聚合(若有 add 合并)
    agg = {}
    for r in rows:
        c = r["code"]
        if c not in agg:
            agg[c] = {"code": c, "name": r["name"] or c, "qty": 0, "cost": 0.0}
        a = agg[c]
        a["cost"] = (a["cost"] * a["qty"] + r["price"] * r["quantity"]) / (a["qty"] + r["quantity"])
        a["qty"] += r["quantity"]
    return list(agg.values())


def _get_live_price(code: str) -> float | None:
    """拉一次实时价(用 qt.gtimg.cn, 不走 em_get 避免缓存)."""
    import urllib.request
    import re
    prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
    url = f"http://qt.gtimg.cn/q={prefix}{code}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = r.read().decode("gbk", errors="ignore")
        m = re.search(r"~" + code + r"~([0-9.]+)~", data)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None


def _position_value(positions: list[dict]) -> tuple[float, float, list[dict]]:
    """返回 (stock_value, cash, enriched_positions)."""
    stock_val = 0.0
    enriched = []
    for p in positions:
        price = _get_live_price(p["code"]) or p["cost"]
        mv = price * p["qty"]
        stock_val += mv
        enriched.append({
            **p,
            "price": price,
            "mv": mv,
            "vol": _annual_vol(p["code"], p["name"]),
        })
    return stock_val, enriched


def simulate(positions: list[dict], cash: float, target: float,
             days: int, n_sims: int = N_SIMS, seed: int | None = None) -> dict:
    """
    几何布朗运动 (GBM) 模拟, 假设各持仓独立。
    返回:
      - hit_prob: 达成目标概率
      - median: 中位数终值
      - p10/p90: 10%/90% 分位
      - paths_sample: 前 20 条路径
    """
    if seed is not None:
        random.seed(seed)

    if not positions:
        # 全现金, 终值 = 现金 * (1+r)^t
        r_daily = (1 + CASH_RATE) ** (1 / 365) - 1
        finals = [cash * (1 + r_daily) ** days for _ in range(n_sims)]
    else:
        n = len(positions)
        # 每日对数收益分布参数
        # mu_annual = 0 (保守, 不假设 alpha)
        # sigma_daily = vol / sqrt(244)
        mus = [0.0] * n
        sigmas = [p["vol"] / (TRADING_DAYS ** 0.5) for p in positions]
        weights = [p["mv"] for p in positions]
        total_stock = sum(weights)
        weights_p = [w / total_stock for w in weights]
        current_values = [p["mv"] for p in positions]
        cash_daily = (1 + CASH_RATE) ** (1 / 365) - 1

        finals = []
        for _ in range(n_sims):
            values = list(current_values)
            cash_sim = cash
            for _d in range(days):
                for i in range(n):
                    # log return ~ N(mu - sigma^2/2, sigma)
                    z = random.gauss(0, 1)
                    ret = mus[i] - 0.5 * sigmas[i] ** 2 + sigmas[i] * z
                    values[i] *= (1 + ret)  # 简化, 实际用 exp(ret)
                cash_sim *= (1 + cash_daily)
            stock_final = sum(values)
            finals.append(stock_final + cash_sim)

    finals.sort()
    hit = sum(1 for f in finals if f >= target) / len(finals)
    return {
        "hit_prob": round(hit, 4),
        "median": round(finals[n_sims // 2], 0),
        "p10": round(finals[n_sims // 10], 0),
        "p25": round(finals[n_sims // 4], 0),
        "p75": round(finals[3 * n_sims // 4], 0),
        "p90": round(finals[9 * n_sims // 10], 0),
        "current": round(sum(p["mv"] for p in positions) + cash, 0),
        "target": target,
        "gap": round(target - (sum(p["mv"] for p in positions) + cash), 0),
        "gap_pct": round((target - (sum(p["mv"] for p in positions) + cash)) /
                         (sum(p["mv"] for p in positions) + cash) * 100, 2),
        "n_sims": n_sims,
        "days": days,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=float, default=100000)
    ap.add_argument("--days", type=int, default=185,
                    help="默认 2026-06-27 到 2026-12-31 ≈ 187 天")
    ap.add_argument("--n-sims", type=int, default=N_SIMS)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    positions = _load_positions()
    stock_val, enriched = _position_value(positions)
    # 现金: 算总资产 - 股票市值 = 现金 (因为 DB 仓均价 × 数量 = 投入本金, 但市值是现价)
    # 实际现金 = 100000(总目标) - 不, 现金 = 当前总资产 - 股票市值
    # 简化: 用 DB 里的 amount 字段反向算
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    invested = conn.execute("""
        SELECT COALESCE(SUM(amount), 0) FROM decisions
        WHERE action IN ('buy','add') AND close_date IS NULL
    """).fetchone()[0]
    conn.close()

    # 当前总资产 = 持仓市值 + 现金
    # 用户提供 ~36,144 元现金, 这里 hardcode 后续可改
    cash = 36144.0
    current_total = stock_val + cash

    print(f"=== 蒙特卡洛目标概率 ===")
    print(f"日期:    {date.today()}")
    print(f"持仓:    {len(enriched)} 只, 市值 {stock_val:,.0f} 元")
    for p in enriched:
        print(f"  {p['code']:<8} {p['name'][:10]:<10} "
              f"qty={p['qty']:<6} 现价={p['price']:<8.3f} "
              f"市值={p['mv']:>10,.0f}  vol={p['vol']:.0%}")
    print(f"现金:    {cash:,.0f} 元")
    print(f"当前总:  {current_total:,.0f} 元")
    print(f"目标:    {args.target:,.0f} 元")
    print(f"缺口:    {args.target - current_total:,.0f} 元 "
          f"({(args.target - current_total) / current_total * 100:.1f}%)")
    print(f"剩余:    {args.days} 天")
    print(f"模拟:    {args.n_sims:,} 次 GBM")
    print()

    result = simulate(enriched, cash, args.target, args.days, args.n_sims, args.seed)
    result["positions"] = enriched
    result["cash"] = cash
    result["date"] = str(date.today())

    print(f"P(达成目标):    {result['hit_prob']:.1%}")
    print(f"中位数终值:      {result['median']:>10,.0f}")
    print(f"P10 终值:        {result['p10']:>10,.0f}  (悲观)")
    print(f"P25 终值:        {result['p25']:>10,.0f}")
    print(f"P75 终值:        {result['p75']:>10,.0f}")
    print(f"P90 终值:        {result['p90']:>10,.0f}  (乐观)")

    # 落盘
    out = cfg.DATA_DIR / "goal_sim_history.json"
    history = []
    if out.exists():
        history = json.loads(out.read_text())
    history.append({k: v for k, v in result.items() if k != "positions"})
    out.write_text(json.dumps(history[-90:], ensure_ascii=False, indent=2))

    if args.json:
        print()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    # 解读
    print()
    print("=== 解读 ===")
    p = result["hit_prob"]
    if p >= 0.7:
        print(f"✅ 高概率达成 (P={p:.0%}). 维持当前策略即可.")
    elif p >= 0.4:
        print(f"⚠️ 中等概率 (P={p:.0%}). 需要额外加仓或提高胜率.")
    elif p >= 0.15:
        print(f"🔴 较低概率 (P={p:.0%}). 缺口过大, 需重新评估目标.")
    else:
        print(f"❌ 极低概率 (P={p:.0%}). 目标不现实, 建议调整.")
    print(f"   期望年化收益需求: {(args.target / current_total) ** (365 / args.days) - 1:.1%}")


if __name__ == "__main__":
    main()
