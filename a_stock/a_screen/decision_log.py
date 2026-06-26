"""decisions 业务层包装。"""
from datetime import datetime
import a_stock.db as db
import a_stock.config as cfg


def add_buy(*, code, strategy, price, quantity, name=None, reason=None,
            brief_snapshot_path=None,
            plan_stop_loss=None, plan_target=None, plan_hold_days=None,
            plan_max_position_pct=None) -> int:
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
    )


def add_add(*, code, strategy, price, quantity, reason=None) -> int:
    return db.insert_decision(
        code=code, strategy=strategy, action="add",
        decision_date=datetime.now().strftime("%Y-%m-%d"),
        decision_time=datetime.now().strftime("%H:%M:%S"),
        price=price, quantity=quantity, reason=reason,
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


def get(decision_id: int):
    with db.conn(cfg.DECISIONS_DB) as c:
        return c.execute("SELECT * FROM decisions WHERE id=?",
                         (decision_id,)).fetchone()