"""MFE/MAE (Maximum Favorable/Adverse Excursion) 持仓过程极值追踪.

借鉴 stockbee-setup-fluency-trainer (docs/references/trading-skills-methodology.md 第2条).
每5min tick由monitor调用update, 追踪每持仓入场后的最大浮盈(MFE)/最大浮亏(MAE).
平仓时记入, 攒样本后回测止损宽度合理性 (验证[D]假设).

MFE = (max_price - entry)/entry  入场后最高价相对成本的涨幅
MAE = (entry - min_price)/entry  入场后最低价相对成本的跌幅
"""
import argparse
import json
from datetime import date
import a_stock.config as cfg

STATE_FILE = cfg.DATA_DIR / "mfe_mae_state.json"


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(s: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2))
    except Exception:
        pass


def _open_positions() -> dict:
    """返回 {code: {qty, cost}} 当前未平仓持仓 (lot制, 成本=加权平均)."""
    from a_stock.db import conn as _db_conn
    with _db_conn(cfg.DECISIONS_DB) as c:
        rows = c.execute(
            "SELECT id, code, price, quantity FROM decisions "
            "WHERE action IN ('buy','add') AND close_date IS NULL"
        ).fetchall()
        reduces = c.execute(
            "SELECT parent_id, SUM(quantity) AS qty FROM decisions "
            "WHERE action='reduce' AND close_date IS NOT NULL GROUP BY parent_id"
        ).fetchall()
    red = {r["parent_id"]: r["qty"] for r in reduces}
    agg = {}
    for r in rows:
        c = r["code"]
        remaining = r["quantity"] - red.get(r["id"], 0)
        if remaining <= 0:
            continue
        if c not in agg:
            agg[c] = {"qty": 0, "cost_sum": 0.0}
        agg[c]["qty"] += remaining
        agg[c]["cost_sum"] += r["price"] * remaining
    return {c: {"qty": v["qty"], "cost": v["cost_sum"] / v["qty"]} for c, v in agg.items()}


def update(prices: dict[str, float]) -> dict:
    """用当前价 {code: price} 更新各持仓 mfe/mae. 返回新state.

    新仓: entry=cost, max/min=price.
    加仓(cost变): 重置 max/min=当前价 (保守, 重新计过程).
    平仓(code消失): 从state删."""
    state = _load_state()
    positions = _open_positions()
    new_state = {}
    for code, px in prices.items():
        if code not in positions:
            continue
        cost = positions[code]["cost"]
        prev = state.get(code)
        if prev is None or abs(prev.get("entry", 0) - cost) > 1e-6:
            # 新仓 或 加仓致成本变 → 重置
            new_state[code] = {"entry": cost, "max_price": px, "min_price": px,
                               "qty": positions[code]["qty"]}
        else:
            new_state[code] = {
                "entry": cost,
                "max_price": max(prev["max_price"], px),
                "min_price": min(prev["min_price"], px),
                "qty": positions[code]["qty"],
            }
    _save_state(new_state)
    return new_state


def snapshot(code: str) -> dict | None:
    """返回某标的 {entry, max_price, min_price, mfe_pct, mae_pct} 或 None."""
    s = _load_state().get(code)
    if not s:
        return None
    entry = s["entry"]
    return {
        "entry": round(entry, 4),
        "max_price": round(s["max_price"], 4),
        "min_price": round(s["min_price"], 4),
        "mfe_pct": round((s["max_price"] - entry) / entry * 100, 2) if entry else 0,
        "mae_pct": round((entry - s["min_price"]) / entry * 100, 2) if entry else 0,
        "qty": s.get("qty", 0),
    }


def report() -> dict:
    """返回全部持仓 mfe/mae 报告."""
    state = _load_state()
    return {code: snapshot(code) for code in state}


def main():
    ap = argparse.ArgumentParser(description="MFE/MAE 持仓过程极值报告")
    ap.add_argument("--update", action="store_true", help="先拉现价更新state")
    args = ap.parse_args()
    if args.update:
        from a_stock.risk_metrics import _load_positions
        positions = _load_positions()
        prices = {p["code"]: p["price"] for p in positions if p.get("price")}
        update(prices)
    r = report()
    print(f"=== MFE/MAE 报告 ({date.today()}) ===")
    if not r:
        print("  (无持仓追踪数据, 跑 --update 或等monitor tick)")
        return
    print(f"  {'代码':<8}{'入场':>9}{'最高':>9}{'最低':>9}{'MFE%':>8}{'MAE%':>8}")
    for code, s in r.items():
        print(f"  {code:<8}{s['entry']:>9.3f}{s['max_price']:>9.3f}{s['min_price']:>9.3f}"
              f"{s['mfe_pct']:>+8.2f}{s['mae_pct']:>+8.2f}")
    print("\n  MFE=入场后最大浮盈%, MAE=入场后最大浮亏%. 攒样本验证止损宽度 (假设[D]).")


if __name__ == "__main__":
    main()
