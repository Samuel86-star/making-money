"""add_add + cost_report 业务函数测试.

覆盖 a_stock/a_screen/decision_log.py 中被 log.py CLI 使用的两个函数.
- add_add: 加仓写入 (log add 命令)
- cost_report: 真实成本报告 (log cost 命令, 铁律[G]防瞎猜的核心)

复用 test_decision_log.py 的 T_ 前缀隔离 + setup/teardown 清理, 防污染生产库.
(2026-06-30 补: 删 test_trading_modal.py 后这俩函数失去唯一覆盖, 此处重建护栏.)
"""
import a_stock.db as db
import a_stock.a_screen.decision_log as dl
import a_stock.config as cfg

T = "T_"  # test code prefix, 与真实数据隔离


def setup_function(_):
    db.init_decisions_db()
    _clean_test_data()


def teardown_function(_):
    _clean_test_data()


def _clean_test_data():
    with db.conn(cfg.DECISIONS_DB) as c:
        c.execute(
            "DELETE FROM decisions WHERE code LIKE ? OR parent_id IN "
            "(SELECT id FROM decisions WHERE code LIKE ?)",
            (f"{T}%", f"{T}%"),
        )
        c.execute("DELETE FROM watchlist WHERE code LIKE ?", (f"{T}%",))


# === add_add: 加仓写入 ===

def test_add_add_returns_id_and_writes_row():
    """add_add 写入 action='add' 行, 返回 id."""
    dl.add_buy(code=f"{T}AA", strategy="mid", price=10.0, quantity=100)
    new_id = dl.add_add(code=f"{T}AA", strategy="mid", price=11.0, quantity=100)
    assert isinstance(new_id, int)
    row = dl.get(new_id)
    assert row["code"] == f"{T}AA"
    assert row["action"] == "add"
    assert row["quantity"] == 100
    assert abs(row["price"] - 11.0) < 1e-6
    assert row["close_date"] is None  # add lot 未平仓


def test_add_add_amount_is_price_times_qty():
    """add_add 自动算 amount = price * quantity."""
    dl.add_buy(code=f"{T}AM", strategy="mid", price=10.0, quantity=100)
    new_id = dl.add_add(code=f"{T}AM", strategy="mid", price=12.5, quantity=200)
    row = dl.get(new_id)
    assert abs(row["amount"] - 12.5 * 200) < 1e-6


# === cost_report: 真实成本报告 (铁律[G]防瞎猜核心) ===

def test_cost_report_none_when_no_position():
    """无持仓返回 None (不抛错, log cost 命令对空代码不应崩)."""
    assert dl.cost_report(f"{T}NONE") is None


def test_cost_report_single_lot_no_reduce():
    """单 lot 无减仓: remaining = buy_qty, realized = 0, cost = 买入价."""
    dl.add_buy(code=f"{T}S1", strategy="mid", price=49.121, quantity=200)
    rep = dl.cost_report(f"{T}S1")
    assert rep is not None
    assert rep["code"] == f"{T}S1"
    assert len(rep["lots"]) == 1
    lot = rep["lots"][0]
    assert lot["buy_qty"] == 200
    assert lot["reduced_qty"] == 0
    assert lot["remaining"] == 200
    assert abs(lot["cost"] - 49.121) < 1e-6
    assert abs(lot["realized"] - 0.0) < 1e-6


def test_cost_report_partial_reduce_reduces_remaining_not_cost():
    """部分减仓: remaining 减少, cost 不变 (lot制, 减仓不改剩余成本).
    对照真实场景: 600276 买200@49.121 减100 → 剩100 成本仍49.121."""
    lot_id = dl.add_buy(code=f"{T}PR", strategy="mid", price=49.121, quantity=200)
    dl.reduce_position(lot_id, 52.67, 100, "partial_take_profit")

    rep = dl.cost_report(f"{T}PR")
    assert len(rep["lots"]) == 1
    lot = rep["lots"][0]
    assert lot["remaining"] == 100          # 200-100
    assert abs(lot["cost"] - 49.121) < 1e-6  # 成本不变
    assert lot["reduced_qty"] == 100
    # realized = (52.67 - 49.121) * 100 = 354.9
    assert abs(lot["realized"] - (52.67 - 49.121) * 100) < 1e-2


def test_cost_report_multiple_lots_independent():
    """多 lot (buy + add_add): 每个 lot 独立核算, 减仓只挂到 parent_id 对应的 lot."""
    lot1 = dl.add_buy(code=f"{T}ML", strategy="mid", price=10.0, quantity=100)
    dl.add_add(code=f"{T}ML", strategy="mid", price=12.0, quantity=200)  # lot2
    # 只减 lot1
    dl.reduce_position(lot1, 15.0, 50, "partial_take_profit")

    rep = dl.cost_report(f"{T}ML")
    assert len(rep["lots"]) == 2
    by_id = {lot["id"]: lot for lot in rep["lots"]}
    # lot1: 买100 减50 → 剩50, realized=(15-10)*50=250
    assert by_id[lot1]["remaining"] == 50
    assert abs(by_id[lot1]["realized"] - 250.0) < 1e-2
    # lot2: 买200 未减 → 剩200, realized=0
    lot2_id = [i for i in by_id if i != lot1][0]
    assert by_id[lot2_id]["remaining"] == 200
    assert abs(by_id[lot2_id]["realized"] - 0.0) < 1e-6


def test_cost_report_add_lot_visible_after_add_add():
    """add_add 写入后 cost_report 能看到新 lot (集成: add_add ↔ cost_report 联动)."""
    dl.add_buy(code=f"{T}AV", strategy="mid", price=5.0, quantity=100)
    rep_before = dl.cost_report(f"{T}AV")
    assert len(rep_before["lots"]) == 1

    dl.add_add(code=f"{T}AV", strategy="mid", price=5.5, quantity=200)
    rep_after = dl.cost_report(f"{T}AV")
    assert len(rep_after["lots"]) == 2
    total_remaining = sum(lot["remaining"] for lot in rep_after["lots"])
    assert total_remaining == 300
    # lot 成本取各自买入价
    costs = sorted(lot["cost"] for lot in rep_after["lots"])
    assert abs(costs[0] - 5.0) < 1e-6
    assert abs(costs[1] - 5.5) < 1e-6
