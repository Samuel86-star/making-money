import py.db as db
import py.a_screen.decision_log as dl
import py.config as cfg


def setup_function(_):
    db.init_decisions_db()
    with db.conn(cfg.DECISIONS_DB) as c:
        c.execute("DELETE FROM decisions")


def test_add_buy_returns_id():
    new_id = dl.add_buy(code="000001", name="平安银行", strategy="short",
                         price=10.0, quantity=1000,
                         plan_stop_loss=9.5, plan_target=11.0)
    assert isinstance(new_id, int)
    row = dl.get(new_id)
    assert row["code"] == "000001"
    assert row["action"] == "buy"
    assert row["close_date"] is None


def test_close_computes_pnl():
    new_id = dl.add_buy(code="000001", strategy="short", price=10.0, quantity=1000)
    dl.close(new_id, "2026-07-01", 11.0, "target")
    row = dl.get(new_id)
    assert row["close_price"] == 11.0
    assert row["pnl_pct"] == 10.0
    assert row["close_reason"] == "target"


def test_list_open_filters_closed():
    id1 = dl.add_buy(code="000001", strategy="short", price=10.0, quantity=1000)
    id2 = dl.add_buy(code="000002", strategy="short", price=20.0, quantity=500)
    dl.close(id1, "2026-07-01", 11.0, "target")
    open_rows = dl.list_open()
    codes = {r["code"] for r in open_rows}
    assert "000001" not in codes
    assert "000002" in codes


def test_update_plan():
    new_id = dl.add_buy(code="000001", strategy="short", price=10.0, quantity=1000,
                        plan_stop_loss=9.0)
    dl.update_plan(new_id, plan_stop_loss=9.5)
    row = dl.get(new_id)
    assert row["plan_stop_loss"] == 9.5