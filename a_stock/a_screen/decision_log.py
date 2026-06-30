"""decisions 业务层包装。"""
from datetime import datetime
import a_stock.db as db
import a_stock.config as cfg


def add_buy(*, code, strategy, price, quantity, name=None, reason=None,
            brief_snapshot_path=None,
            plan_stop_loss=None, plan_target=None, plan_hold_days=None,
            plan_max_position_pct=None, setup=None) -> int:
    if not name:
        # 简化:不查名称,留给前端展示
        name = code
    return db.insert_decision(
        code=code, name=name, strategy=strategy, action="buy",
        decision_date=datetime.now().strftime("%Y-%m-%d"),
        decision_time=datetime.now().strftime("%H:%M:%S"),
        price=price, quantity=quantity,
        reason=reason, brief_snapshot_path=brief_snapshot_path,
        plan_stop_loss=plan_stop_loss, plan_target=plan_target,
        plan_hold_days=plan_hold_days,
        plan_max_position_pct=plan_max_position_pct,
        setup=setup,
    )


def add_add(*, code, strategy, price, quantity, reason=None, setup=None) -> int:
    return db.insert_decision(
        code=code, strategy=strategy, action="add",
        decision_date=datetime.now().strftime("%Y-%m-%d"),
        decision_time=datetime.now().strftime("%H:%M:%S"),
        price=price, quantity=quantity, reason=reason, setup=setup,
    )


def close(decision_id: int, close_date: str, close_price: float, close_reason: str) -> None:
    with db.conn(cfg.DECISIONS_DB) as c:
        row = c.execute(
            "SELECT price FROM decisions WHERE id=?", (decision_id,)
        ).fetchone()
    if not row:
        raise ValueError(f"no decision {decision_id}")
    pnl_pct = (close_price - row["price"]) / row["price"] * 100 if row["price"] else 0
    db.update_decision_close(decision_id, close_date, close_price, close_reason, pnl_pct)


def update_plan(decision_id: int, **plan_fields) -> None:
    if not plan_fields:
        return
    sets = ",".join(f"{k}=?" for k in plan_fields)
    with db.conn(cfg.DECISIONS_DB) as c:
        c.execute(f"UPDATE decisions SET {sets}, updated_at=datetime('now') WHERE id=?",
                  (*plan_fields.values(), decision_id))


def list_open(strategy: str | None = None):
    with db.conn(cfg.DECISIONS_DB) as c:
        if strategy:
            return c.execute(
                "SELECT * FROM decisions WHERE close_date IS NULL AND strategy=? ORDER BY decision_date DESC",
                (strategy,)).fetchall()
        return c.execute(
            "SELECT * FROM decisions WHERE close_date IS NULL ORDER BY decision_date DESC"
        ).fetchall()


def cost_report(code: str) -> dict | None:
    """某标的真实成本报告 (防瞎猜, 06-29教训).

    返回 {code, lots:[{id,date,price,buy_qty,reduced_qty,remaining,cost,realized}]}
    每个未平仓 buy/add lot: 剩余量 = buy_qty - Σ挂该lot的reduce量, 成本=lot买入价(不变).
    realized = Σ (reduce价 - lot成本) * reduce量."""
    with db.conn(cfg.DECISIONS_DB) as c:
        lots = c.execute(
            "SELECT * FROM decisions WHERE code=? AND action IN ('buy','add') "
            "AND close_date IS NULL ORDER BY id", (code,)).fetchall()
        if not lots:
            return None
        reduces = c.execute(
            "SELECT * FROM decisions WHERE code=? AND action='reduce' "
            "AND close_date IS NOT NULL ORDER BY id", (code,)).fetchall()
    out = {"code": code, "lots": []}
    for lot in lots:
        linked = [r for r in reduces if r["parent_id"] == lot["id"]]
        reduced_qty = sum(r["quantity"] for r in linked)
        remaining = lot["quantity"] - reduced_qty
        realized = sum((r["price"] - lot["price"]) * r["quantity"] for r in linked)
        out["lots"].append({
            "id": lot["id"], "date": lot["decision_date"],
            "cost": lot["price"], "buy_qty": lot["quantity"],
            "reduced_qty": reduced_qty, "remaining": remaining,
            "realized": round(realized, 2),
        })
    return out


def get(decision_id: int):
    with db.conn(cfg.DECISIONS_DB) as c:
        return c.execute("SELECT * FROM decisions WHERE id=?",
                         (decision_id,)).fetchone()


def reduce_position(parent_id: int, reduce_price: float, reduce_qty: int, reason: str) -> int:
    """Partial close of a position lot. Creates a linked reduce row with pnl, closes it immediately."""
    with db.conn(cfg.DECISIONS_DB) as c:
        parent = c.execute(
            "SELECT * FROM decisions WHERE id=? AND close_date IS NULL AND action IN ('buy', 'add')",
            (parent_id,)
        ).fetchone()
    if not parent:
        raise ValueError(f"no open buy/add decision {parent_id}")

    pnl_pct = (reduce_price - parent["price"]) / parent["price"] * 100

    new_id = db.insert_decision(
        code=parent["code"], name=parent["name"], strategy=parent["strategy"],
        action="reduce",
        decision_date=datetime.now().strftime("%Y-%m-%d"),
        decision_time=datetime.now().strftime("%H:%M:%S"),
        price=reduce_price, quantity=reduce_qty,
        reason=reason,
        parent_id=parent_id,
    )

    db.update_decision_close(new_id, datetime.now().strftime("%Y-%m-%d"), reduce_price, reason, pnl_pct)

    return new_id


def add_to_watchlist(code: str, name: str | None = None, theme: str | None = None,
                     note: str | None = None) -> None:
    with db.conn(cfg.DECISIONS_DB) as c:
        c.execute(
            "INSERT OR REPLACE INTO watchlist (code, name, theme, note, added_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (code, name, theme, note),
        )


def remove_from_watchlist(code: str) -> None:
    with db.conn(cfg.DECISIONS_DB) as c:
        c.execute("DELETE FROM watchlist WHERE code=?", (code,))


def list_watchlist():
    with db.conn(cfg.DECISIONS_DB) as c:
        return c.execute("SELECT * FROM watchlist ORDER BY added_at DESC").fetchall()