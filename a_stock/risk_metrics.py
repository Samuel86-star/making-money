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

# 板块分类关键词 (顺序敏感: 先匹配先返回, 避免误判)
_SECTOR_RULES = [
    ("科技",   ["芯片", "半导体", "信息技术", "软件", "电子", "通信", "5G", "AI", "算力"]),
    ("医药",   ["医药", "医疗", "生物", "恒瑞", "药", "康"]),
    ("消费",   ["消费", "食品", "白酒", "酒", "五粮液", "茅台", "家电", "零售"]),
    ("金融",   ["金融", "券商", "银行", "保险", "东方财富", "证券"]),
    ("新能源", ["新能源", "光伏", "锂电", "储能", "碳中和"]),
    ("宽基",   ["创业板", "沪深300", "中证500", "上证50", "科创", "宽基", "指数"]),
]


def classify_sector(code: str, name: str) -> str:
    """标的板块分类. 优先名称关键词, fallback 宽基ETF/其他."""
    n = (name or "")
    for sector, keywords in _SECTOR_RULES:
        if any(k in n for k in keywords):
            return sector
    # ETF 但无明确板块 → 宽基; 否则其他
    if "etf" in n.lower() or "ETF" in n:
        return "宽基"
    return "其他"


def _classify_kind(name: str) -> str:
    n = (name or "").lower()
    if "etf" in n or "指数" in n:
        if any(k in n for k in ("50", "300", "500", "创业", "创业板", "1599", "5103", "5105")):
            return "etf_index"
        return "etf_sector"
    return "stock_mid"


def _annual_vol(code: str, name: str) -> float:
    return DEFAULT_VOL_ANNUAL[_classify_kind(name)]


def sector_concentration(positions: list[dict]) -> dict[str, float]:
    """板块集中度: 各板块市值占比 (%). 供压力测试 + 风险提示."""
    by_sector: dict[str, float] = {}
    total_mv = sum(p["mv"] for p in positions) or 1
    for p in positions:
        sec = classify_sector(p["code"], p["name"])
        by_sector[sec] = by_sector.get(sec, 0) + p["mv"]
    return {s: round(mv / total_mv * 100, 2) for s, mv in by_sector.items()}


def _portfolio_returns(positions: list[dict],
                       returns_by_code: dict[str, list[float]]) -> list[float]:
    """组合日收益序列 = 各标的日收益按市值加权. 缺数据的标的视为 0 收益."""
    total_mv = sum(p["mv"] for p in positions)
    if total_mv <= 0:
        return []
    # 对齐长度 (取各标的序列最长, 缺位补 0)
    max_len = max((len(returns_by_code.get(p["code"], [])) for p in positions), default=0)
    if max_len == 0:
        return []
    pr = [0.0] * max_len
    for p in positions:
        code = p["code"]
        w = p["mv"] / total_mv
        rs = returns_by_code.get(code, [])
        for i in range(max_len):
            pr[i] += w * (rs[i] if i < len(rs) else 0.0)
    return pr


def stress_test(positions: list[dict], total: float,
                sector_shocks: dict[str, float] | None = None,
                market_crash: float | None = None) -> list[dict]:
    """情景压力测试. 返回 [{name, loss, loss_pct}].
    sector_shocks: {板块: 跌幅} 如 {"消费": -0.10}
    market_crash: 全市场跌幅 如 -0.08"""
    sector_shocks = sector_shocks or {}
    sec_mv = {}
    for p in positions:
        sec = classify_sector(p["code"], p["name"])
        sec_mv[sec] = sec_mv.get(sec, 0) + p["mv"]
    scenarios = []
    # 板块冲击场景
    for sec, shock in sector_shocks.items():
        mv = sec_mv.get(sec, 0)
        loss = mv * abs(shock)  # shock 负 → 损失正
        scenarios.append({
            "name": f"{sec}板块跌{abs(shock)*100:.0f}%",
            "loss": round(loss), "loss_pct": round(loss / total * 100, 2) if total else 0,
        })
    # 全市场暴跌场景
    if market_crash is not None:
        stock_mv = sum(p["mv"] for p in positions)
        loss = stock_mv * abs(market_crash)
        scenarios.append({
            "name": f"全市场暴跌{abs(market_crash)*100:.0f}%",
            "loss": round(loss), "loss_pct": round(loss / total * 100, 2) if total else 0,
        })
    # 默认场景: 无指定时跑一组标准压力 (消费-10%/科技-12%/全市场-8%)
    if not sector_shocks and market_crash is None:
        std = {"消费": -0.10, "科技": -0.12, "金融": -0.10, "医药": -0.10}
        scenarios = stress_test(positions, total, sector_shocks=std)
        scenarios += stress_test(positions, total, market_crash=-0.08)
    return scenarios


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
    """当前持仓 = sum(buy/add) - sum(reduce). reduce 行 linked parent_id.

    成本基 (06-29教训): lot 制下剩余成本=父lot买入价; 多 lot 时取移动加权平均.
    返回每标的 cost / mv / unrealized_pnl."""
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, code, name, price, quantity
        FROM decisions
        WHERE action IN ('buy','add') AND close_date IS NULL
    """).fetchall()
    reduces = conn.execute("""
        SELECT parent_id, SUM(quantity) AS qty
        FROM decisions
        WHERE action='reduce' AND close_date IS NOT NULL
        GROUP BY parent_id
    """).fetchall()
    conn.close()
    red_by_parent = {r["parent_id"]: r["qty"] for r in reduces}
    agg = {}
    for r in rows:
        c = r["code"]
        if c not in agg:
            agg[c] = {"code": c, "name": r["name"] or c, "qty": 0, "cost_sum": 0.0}
        remaining = r["quantity"] - red_by_parent.get(r["id"], 0)
        if remaining > 0:
            agg[c]["qty"] += remaining
            agg[c]["cost_sum"] += r["price"] * remaining
    out = []
    for c, p in agg.items():
        if p["qty"] <= 0:
            continue
        px = _live_price(c) or 0
        cost = p["cost_sum"] / p["qty"] if p["qty"] else 0
        out.append({**p, "price": px, "cost": cost, "mv": px * p["qty"],
                    "unrealized_pnl": (px - cost) * p["qty"],
                    "vol": _annual_vol(c, p["name"])})
    return out


def _stop_for(code: str, cost: float, name: str) -> float | None:
    """取某标的止损价: 优先 db plan_stop_loss, 缺则 ATR 结构止损.

    docs/references/trading-skills-methodology.md 第1条 Portfolio Heat 用."""
    from a_stock.db import conn as _db_conn
    with _db_conn(cfg.DECISIONS_DB) as c:
        row = c.execute(
            "SELECT MIN(plan_stop_loss) AS s FROM decisions "
            "WHERE code=? AND action IN ('buy','add') AND close_date IS NULL "
            "AND plan_stop_loss IS NOT NULL", (code,)
        ).fetchone()
    if row and row["s"]:
        return float(row["s"])
    # fallback: ATR 结构止损
    try:
        from a_stock.ohlcv import atr, struct_stop_loss
        a = atr(code)
        return struct_stop_loss(cost, a) if a else cost * 0.97
    except Exception:
        return cost * 0.97  # 默认3%止损


def portfolio_heat(positions: list[dict], total: float, limit_pct: float = 6.0) -> dict:
    """组合总风险敞口 = Σ (成本-止损)×持仓量. (Portfolio Heat)

    借鉴 position-sizer/exposure-coach (docs/references/trading-skills-methodology.md 第1条).
    不是单仓%, 是全部未平仓位的总下行风险. 超 limit_pct%(默认6%) → breach.
    保护100k下行: 量化"若全触及止损总亏多少"."""
    if not positions or total <= 0:
        return {"heat": 0.0, "heat_pct": 0.0, "breach": False, "by_position": [], "limit_pct": limit_pct}
    by_pos = []
    heat = 0.0
    for p in positions:
        cost = p.get("cost", 0)
        stop = _stop_for(p["code"], cost, p.get("name", ""))
        if stop is None or stop >= cost:
            risk_per_share = 0.0
        else:
            risk_per_share = cost - stop
        risk = risk_per_share * p["qty"]
        heat += risk
        by_pos.append({"code": p["code"], "qty": p["qty"], "cost": round(cost, 4),
                       "stop": round(stop, 4) if stop else None,
                       "risk": round(risk)})
    heat_pct = round(heat / total * 100, 2)
    return {"heat": round(heat), "heat_pct": heat_pct,
            "breach": heat_pct > limit_pct, "by_position": by_pos, "limit_pct": limit_pct}


def check_reduce_label_consistency() -> list[dict]:
    """校验 reduce 标签与 pnl 符号一致 (06-29教训: partial_take_profit 不应 pnl<0).

    返回异常列表 [{id, code, reason, pnl_pct}]."""
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, code, close_reason, pnl_pct FROM decisions
        WHERE action='reduce' AND close_date IS NOT NULL AND pnl_pct IS NOT NULL
    """).fetchall()
    conn.close()
    anomalies = []
    for r in rows:
        reason = r["close_reason"] or ""
        pnl = r["pnl_pct"] or 0
        if "take_profit" in reason and pnl < 0:
            anomalies.append({"id": r["id"], "code": r["code"],
                              "reason": reason, "pnl_pct": round(pnl, 2)})
        elif "stop_loss" in reason and pnl > 0:
            anomalies.append({"id": r["id"], "code": r["code"],
                              "reason": reason, "pnl_pct": round(pnl, 2)})
    return anomalies


def _load_returns_by_code(positions: list[dict], lookback: int = 60) -> dict[str, list[float]]:
    """从 parquet 读各标的日收益率序列 (供 Sortino). 缺数据跳过."""
    import pandas as pd
    out: dict[str, list[float]] = {}
    for p in positions:
        f = cfg.OHLCV_DIR / f"{p['code']}.parquet"
        if not f.exists():
            continue
        try:
            df = pd.read_parquet(f).tail(lookback)
            closes = df["Close"].tolist()
            if len(closes) < 5:
                continue
            rets = [(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))
                    if closes[i-1] > 0]
            out[p["code"]] = rets
        except Exception:
            continue
    return out


def compute(positions: list[dict], cash: float = 36144.0, risk_free: float = 0.02,
            rho: float = 0.3, returns_by_code: dict[str, list[float]] | None = None) -> dict:
    """组合风险. 假设内部相关性 rho (A 股经验值 0.3).
    returns_by_code: 各标的日收益序列 (供 Sortino 真实现); 缺则 Sortino 降级为 Sharpe."""
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

    # Sortino 真实现: 用组合日收益序列算下行波动率 (仅计负收益)
    if returns_by_code:
        pr = _portfolio_returns(positions, returns_by_code)
        downside = [r for r in pr if r < 0]
        if downside:
            downside_var = sum(r * r for r in downside) / len(pr)  # 用全样本均值, 非仅负数
            downside_daily = downside_var ** 0.5
            downside_annual = downside_daily * (TRADING_DAYS ** 0.5)
            # Sortino: (预期收益 - rf) / 下行波动; 这里预期收益用 0 (无历史均值假设), 与 Sharpe 一致
            sortino = (0.0 - risk_free) / downside_annual if downside_annual else 0.0
            sortino = round(sortino, 2)
        else:
            sortino = float("inf")  # 无下行风险
    else:
        sortino = round(sharpe, 2)  # 降级: 无收益序列时与 Sharpe 一致

    return {
        "total_mv": round(total_stock),
        "cash": round(cash),
        "total": round(total),
        "n_positions": n,
        "portfolio_vol_annual": round(adj_vol, 4),
        "daily_vol": round(daily_vol, 4),
        "sharpe": round(sharpe, 2),
        "sortino": sortino,
        "var_95_1d": round(var_95_1d),
        "var_95_1d_pct": round(var_95_1d / total * 100, 2),
        "max_dd_5d_95": round(max_dd_5d_95),
        "max_dd_5d_95_pct": round(max_dd_5d_95 / total * 100, 2),
        "hhi": round(hhi, 4),
        "largest_pct": round(largest * 100, 2),
        "positions": [
            {"code": p["code"], "name": p["name"][:10],
             "weight": round(p["mv"] / total * 100, 2),
             "vol": p["vol"], "mv": round(p["mv"]),
             "cost": round(p.get("cost", 0), 4),
             "unrealized_pnl": round(p.get("unrealized_pnl", 0))}
            for p in positions
        ],
        "total_unrealized_pnl": round(sum(p.get("unrealized_pnl", 0) for p in positions)),
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
    returns_by_code = _load_returns_by_code(positions) if positions else {}
    r = compute(positions, args.cash, args.rf, returns_by_code=returns_by_code)

    print(f"=== 组合风险报告 ({date.today()}) ===\n")
    print(f"股票市值:   {r['total_mv']:>10,} 元 ({len(positions)} 只)")
    print(f"现金:       {r['cash']:>10,} 元")
    print(f"总资产:     {r['total']:>10,} 元\n")
    print(f"组合年化波动率:  {r['portfolio_vol_annual']:.1%}")
    print(f"日波动率:        {r['daily_vol']:.2%}")
    print(f"Sharpe (μ=0):    {r['sharpe']:.2f}")
    sortino_str = "inf (无下行)" if r["sortino"] == float("inf") else f"{r['sortino']:.2f}"
    print(f"Sortino:         {sortino_str}"
          + ("" if returns_by_code else "  (无收益序列, 降级=Sharpe)"))
    print(f"1d VaR 95%:      {r['var_95_1d']:>6,} 元 ({r['var_95_1d_pct']:.2f}%)")
    print(f"5d MaxDD 95%:    {r['max_dd_5d_95']:>6,} 元 ({r['max_dd_5d_95_pct']:.2f}%)")
    print(f"HHI 集中度:      {r['hhi']:.4f}  (1/N={1/max(r['n_positions'],1):.4f})")
    print(f"最大单仓占比:    {r['largest_pct']:.1f}%\n")
    print("持仓权重:")
    if r["positions"]:
        max_w = max(p["weight"] for p in r["positions"])
        for p in r["positions"]:
            print(_bar(p["code"], p["weight"], max_w))

    # 持仓成本与浮盈 (06-29教训: 报盈亏前必查真实成本)
    if positions:
        print("\n=== 持仓成本与浮盈 ===")
        print(f"  {'代码':<8}{'持仓':<7}{'成本':<10}{'现价':<10}{'浮盈':<10}")
        for p, rp in zip(positions, r["positions"]):
            pnl = rp["unrealized_pnl"]
            print(f"  {p['code']:<8}{p['qty']:<7}{p.get('cost',0):<10.4f}{p['price']:<10.4f}{pnl:<+10.0f}")
        print(f"  合计浮盈: {r['total_unrealized_pnl']:+,} 元")

    # 板块集中度
    if positions:
        print("\n=== 板块集中度 ===")
        sc = sector_concentration(positions)
        for sec, pct in sorted(sc.items(), key=lambda x: -x[1]):
            print(f"  {sec:<6} {pct:>6.1f}%")

    # Portfolio Heat (组合总风险敞口, docs/references 第1条)
    if positions:
        print("\n=== Portfolio Heat (总风险敞口) ===")
        ph = portfolio_heat(positions, r["total"])
        print(f"  总风险: {ph['heat']:,} 元 ({ph['heat_pct']:.2f}%, 上限{ph['limit_pct']:.0f}%)")
        for bp in ph["by_position"]:
            stop_s = f"{bp['stop']:.3f}" if bp["stop"] else "无"
            print(f"    {bp['code']:<8} 持{bp['qty']:<6} 成本{bp['cost']:<8} 止损{stop_s:<8} 风险{bp['risk']:>6,}")
        if ph["breach"]:
            print(f"  ⚠️  Heat {ph['heat_pct']:.1f}% > {ph['limit_pct']:.0f}% 上限, 减仓降风险")

    # 压力测试
    if positions:
        print("\n=== 压力测试 ===")
        total = r["total"] or 1
        scenarios = stress_test(positions, total)
        for s in scenarios:
            print(f"  {s['name']:<18} 损失 {s['loss']:>6,} 元 ({s['loss_pct']:.2f}%)")

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
    # 板块集中度提示
    if positions:
        sc = sector_concentration(positions)
        max_sec, max_pct = max(sc.items(), key=lambda x: x[1]) if sc else ("", 0)
        if max_pct > 50:
            warnings.append(f"  ⚠️  {max_sec}板块占 {max_pct:.0f}% > 50%, 板块集中风险")
    # reduce 标签一致性校验 (06-29教训: take_profit 不应 pnl<0)
    anomalies = check_reduce_label_consistency()
    if anomalies:
        for a in anomalies:
            warnings.append(f"  ⚠️  id={a['id']} {a['code']} 标签{a['reason']}与pnl{a['pnl_pct']:+.1f}%矛盾")
    if not warnings:
        warnings.append("  ✅ 当前风险在可控范围")
    print("\n".join(warnings))

    if args.json:
        import json
        print()
        print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
