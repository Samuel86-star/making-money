import a_stock.db as db
import a_stock.a_screen.decision_log as dl
import a_stock.config as cfg

# 测试数据用 T_ 前缀,与真实数据隔离。setup_function 只清 T_ 前缀
T = "T_"  # test code prefix


def setup_function(_):
    db.init_decisions_db()
    _clean_test_data()


def teardown_function(_):
    """测试后清 T_ 数据, 防残留污染生产库."""
    _clean_test_data()


def _clean_test_data():
    with db.conn(cfg.DECISIONS_DB) as c:
        # 只清测试数据,保留真实持仓和 watchlist
        c.execute("DELETE FROM decisions WHERE code LIKE ? OR parent_id IN (SELECT id FROM decisions WHERE code LIKE ?)", (f"{T}%", f"{T}%"))
        c.execute("DELETE FROM watchlist WHERE code LIKE ?", (f"{T}%",))


def test_add_buy_returns_id():
    new_id = dl.add_buy(code=f"{T}0001", name="测试平安银行", strategy="short",
                         price=10.0, quantity=1000,
                         plan_stop_loss=9.5, plan_target=11.0)
    assert isinstance(new_id, int)
    row = dl.get(new_id)
    assert row["code"] == f"{T}0001"
    assert row["action"] == "buy"
    assert row["close_date"] is None


def test_close_computes_pnl():
    new_id = dl.add_buy(code=f"{T}0001", strategy="short", price=10.0, quantity=1000)
    dl.close(new_id, "2026-07-01", 11.0, "target")
    row = dl.get(new_id)
    assert row["close_price"] == 11.0
    assert row["pnl_pct"] == 10.0
    assert row["close_reason"] == "target"


def test_list_open_filters_closed():
    id1 = dl.add_buy(code=f"{T}0001", strategy="short", price=10.0, quantity=1000)
    id2 = dl.add_buy(code=f"{T}0002", strategy="short", price=20.0, quantity=500)
    dl.close(id1, "2026-07-01", 11.0, "target")
    open_rows = dl.list_open()
    codes = {r["code"] for r in open_rows}
    assert f"{T}0001" not in codes
    assert f"{T}0002" in codes


def test_update_plan():
    new_id = dl.add_buy(code=f"{T}0001", strategy="short", price=10.0, quantity=1000,
                        plan_stop_loss=9.0)
    dl.update_plan(new_id, plan_stop_loss=9.5)
    row = dl.get(new_id)
    assert row["plan_stop_loss"] == 9.5


def test_reduce_position_creates_linked_row_with_pnl():
    parent_id = dl.add_buy(code=f"{T}0001", strategy="short", price=10.0, quantity=1000)
    reduce_id = dl.reduce_position(parent_id, reduce_price=11.0, reduce_qty=200,
                                   reason="partial_take_profit")
    row = dl.get(reduce_id)
    assert row["action"] == "reduce"
    assert row["parent_id"] == parent_id
    assert row["price"] == 11.0
    assert row["quantity"] == 200
    assert row["close_date"] is not None
    assert row["close_price"] == 11.0
    assert row["close_reason"] == "partial_take_profit"
    assert row["pnl_pct"] == 10.0

    # Parent remains open
    parent = dl.get(parent_id)
    assert parent["close_date"] is None


def test_watchlist_add_and_list():
    dl.add_to_watchlist(f"{T}2415", name="测试海康威视", theme="监控/AI", note="测试")
    rows = dl.list_watchlist()
    codes = {r["code"] for r in rows}
    assert f"{T}2415" in codes


def test_watchlist_remove():
    dl.add_to_watchlist(f"{T}2415", name="测试海康威视", theme="监控/AI")
    dl.remove_from_watchlist(f"{T}2415")
    rows = dl.list_watchlist()
    codes = {r["code"] for r in rows}
    assert f"{T}2415" not in codes