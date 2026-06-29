"""资产条数据: 总资产/市值/现金/浮盈/距目标."""
import sqlite3
from datetime import date
import a_stock.config as cfg

TARGET = 100000.0


def _positions_total_mv() -> float:
    from a_stock.risk_metrics import _load_positions
    return sum(p.get("mv", 0) for p in _load_positions())


def _total_unrealized() -> float:
    from a_stock.risk_metrics import _load_positions
    return sum(p.get("unrealized_pnl", 0) for p in _load_positions())


def _realized_today() -> float:
    """今日已实现盈亏 (reduce行 pnl挂回parent成本)."""
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT r.price AS rp, r.quantity AS rq, b.price AS bp
        FROM decisions r JOIN decisions b ON r.parent_id=b.id
        WHERE r.action='reduce' AND r.close_date=?
    """, (date.today().isoformat(),)).fetchall()
    conn.close()
    return sum((r["rp"] - r["bp"]) * r["rq"] for r in rows)


def collect_asset_bar(cash: float) -> dict:
    mv = _positions_total_mv()
    total = mv + cash
    return {
        "total": round(total),
        "stock_mv": round(mv),
        "cash": round(cash),
        "unrealized": round(_total_unrealized()),
        "realized": round(_realized_today()),
        "target_pct": round(total / TARGET * 100, 1),
    }