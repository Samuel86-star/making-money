"""Tests for a_stock.db — SQLite wrappers.

DB 隔离: monkeypatch cfg.DECISIONS_DB/SCREENER_DB 指向 tmp_path, 不污染生产库.
代码用 T_ 前缀 (非真实股票代码). 历史: 旧版用真实 000858+生产DB, 每跑一次污染 2 条."""
import sqlite3
import pytest
import a_stock.config as cfg
import a_stock.db as db


@pytest.fixture
def isolated_dbs(tmp_path, monkeypatch):
    """每个测试用独立 tmp DB, 不碰生产 data/decisions.sqlite."""
    dec = tmp_path / "decisions.sqlite"
    scr = tmp_path / "screener.sqlite"
    monkeypatch.setattr(cfg, "DECISIONS_DB", dec)
    monkeypatch.setattr(cfg, "SCREENER_DB", scr)
    # db.py 内 conn(cfg.DECISIONS_DB) 读 monkeypatch 后的路径
    db.init_decisions_db()
    db.init_screener_db()
    return dec, scr


def test_init_creates_tables(isolated_dbs):
    dec, scr = isolated_dbs
    with db.conn(dec) as c:
        rows = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {r[0] for r in rows}
        assert "decisions" in names
        assert "watchlist" in names
    with db.conn(scr) as c:
        rows = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {r[0] for r in rows}
        assert "candidate_history" in names
        assert "sector_history" in names
        assert "daily_summary" in names


def test_insert_and_query_decision(isolated_dbs):
    dec, _ = isolated_dbs
    new_id = db.insert_decision(
        code="T_858", name="T_五粮液", strategy="short", action="buy",
        decision_date="2026-06-26", price=168.5, quantity=100,
        reason="板块共振",
        brief_snapshot_path="data/screen/briefs/T_858/2026-06-26.md",
        plan_stop_loss=160, plan_target=185, plan_hold_days=5,
    )
    with db.conn(dec) as c:
        row = c.execute(
            "SELECT code, name, strategy, price FROM decisions WHERE id=?",
            (new_id,),
        ).fetchone()
        assert row[0] == "T_858"
        assert row[1] == "T_五粮液"
        assert row[2] == "short"
        assert row[3] == 168.5


def test_close_decision_updates_pnl(isolated_dbs):
    dec, _ = isolated_dbs
    new_id = db.insert_decision(
        code="T_858", name="T_五粮液", strategy="short", action="buy",
        decision_date="2026-06-26", price=100.0, quantity=100,
    )
    db.update_decision_close(new_id, "2026-06-30", 110.0, "target", 10.0)
    with db.conn(dec) as c:
        row = c.execute(
            "SELECT close_price, close_reason, pnl_pct FROM decisions WHERE id=?",
            (new_id,),
        ).fetchone()
        assert row[0] == 110.0
        assert row[1] == "target"
        assert row[2] == 10.0
