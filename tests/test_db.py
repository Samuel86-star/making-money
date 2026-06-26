"""Tests for py.db — SQLite wrappers."""
import sqlite3
import py.db as db
import py.config as cfg


def test_init_creates_tables():
    db.init_decisions_db()
    db.init_screener_db()
    with db.conn(cfg.DECISIONS_DB) as c:
        rows = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {r[0] for r in rows}
        assert "decisions" in names
        assert "watchlist" in names
    with db.conn(cfg.SCREENER_DB) as c:
        rows = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {r[0] for r in rows}
        assert "candidate_history" in names
        assert "sector_history" in names
        assert "daily_summary" in names


def test_insert_and_query_decision():
    db.init_decisions_db()
    new_id = db.insert_decision(
        code="000858", name="五粮液", strategy="short", action="buy",
        decision_date="2026-06-26", price=168.5, quantity=100,
        reason="板块共振",
        brief_snapshot_path="data/screen/briefs/000858/2026-06-26.md",
        plan_stop_loss=160, plan_target=185, plan_hold_days=5,
    )
    with db.conn(cfg.DECISIONS_DB) as c:
        row = c.execute(
            "SELECT code, name, strategy, price FROM decisions WHERE id=?",
            (new_id,),
        ).fetchone()
        assert row[0] == "000858"
        assert row[1] == "五粮液"
        assert row[2] == "short"
        assert row[3] == 168.5


def test_close_decision_updates_pnl():
    db.init_decisions_db()
    new_id = db.insert_decision(
        code="000858", name="五粮液", strategy="short", action="buy",
        decision_date="2026-06-26", price=100.0, quantity=100,
    )
    db.update_decision_close(new_id, "2026-06-30", 110.0, "target", 10.0)
    with db.conn(cfg.DECISIONS_DB) as c:
        row = c.execute(
            "SELECT close_price, close_reason, pnl_pct FROM decisions WHERE id=?",
            (new_id,),
        ).fetchone()
        assert row[0] == 110.0
        assert row[1] == "target"
        assert row[2] == 10.0