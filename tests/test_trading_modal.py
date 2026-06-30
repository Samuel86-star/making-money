"""trading_modal 单元测试. 100股铁律 + 选最大lot逻辑 + 集成写入."""
import pytest
import a_stock.config as cfg
import a_stock.db as db
from a_stock.web import trading_modal
from a_stock.a_screen.decision_log import add_buy, add_add, reduce_position, cost_report


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """DB 隔离: tmp_path 替代生产库, 跑完清空."""
    dec = tmp_path / "decisions.sqlite"
    monkeypatch.setattr(cfg, "DECISIONS_DB", dec)
    db.init_decisions_db()
    return dec


# === 100股整数倍校验 ===

def test_validate_lot_100_ok_add():
    ok, msg = trading_modal._validate_lot(100, "add")
    assert ok and not msg


def test_validate_lot_100_ok_reduce():
    ok, msg = trading_modal._validate_lot(100, "reduce")
    assert ok and not msg


@pytest.mark.parametrize("qty", [50, 150, 199, 250, 1, 99])
def test_validate_lot_non_100x_rejects(qty):
    """A股铁律: 50/150/199/250 全拒. (记忆: 见 a-share-trading-units.md)"""
    ok, msg = trading_modal._validate_lot(qty, "add")
    assert not ok, f"应拒 {qty}"
    assert "100" in msg


def test_validate_lot_zero_rejects():
    ok, _ = trading_modal._validate_lot(0, "add")
    assert not ok


def test_validate_lot_negative_rejects():
    ok, _ = trading_modal._validate_lot(-100, "reduce")
    assert not ok


def test_validate_lot_large_ok():
    """大额 (10000) 通过."""
    ok, _ = trading_modal._validate_lot(10000, "add")
    assert ok


# === 选最大lot (减仓时) ===

def test_pick_largest_lot_picks_max_remaining(isolated_db):
    """多lot时, 选剩余量最大的lot作为减仓parent."""
    add_buy(code="T_LRG", strategy="mid", price=10.0, quantity=200)  # lot 1: 200
    add_add(code="T_LRG", strategy="mid", price=12.0, quantity=500)  # lot 2: 500
    add_add(code="T_LRG", strategy="mid", price=8.0,  quantity=100)  # lot 3: 100

    picked = trading_modal._pick_largest_lot("T_LRG")
    assert picked is not None
    rep = cost_report("T_LRG")
    picked_lot = next(lot for lot in rep["lots"] if lot["id"] == picked)
    assert picked_lot["remaining"] == 500  # lot 2 剩500, 最大


def test_pick_largest_lot_considers_reduced(isolated_db):
    """减仓过的lot, 剩余量可能不是最大, 应选真正剩余最大的."""
    lot1 = add_buy(code="T_RED", strategy="mid", price=10.0, quantity=1000)
    add_add(code="T_RED", strategy="mid", price=11.0, quantity=200)

    # 减仓 lot1 800 → 剩200
    reduce_position(lot1, 12.0, 800, "partial_take_profit")

    picked = trading_modal._pick_largest_lot("T_RED")
    rep = cost_report("T_RED")
    picked_lot = next(lot for lot in rep["lots"] if lot["id"] == picked)
    # lot1 剩200, lot2 剩200, 平手选max返回第一个最大
    assert picked_lot["remaining"] == 200


def test_pick_largest_lot_no_position_returns_none(isolated_db):
    """无持仓返回 None (不抛错)."""
    assert trading_modal._pick_largest_lot("T_NONE") is None


# === 集成: add_add + reduce_position 真实写入 + cost_report 反映 ===

def test_add_add_writes_lot_visible_in_cost_report(isolated_db):
    add_buy(code="T_INT", strategy="mid", price=5.0, quantity=100)
    add_add(code="T_INT", strategy="mid", price=5.5, quantity=200)

    rep = cost_report("T_INT")
    assert rep is not None
    total_remaining = sum(lot["remaining"] for lot in rep["lots"])
    assert total_remaining == 300
    # lot 成本取买入价 (不减仓不改)
    assert abs(rep["lots"][0]["cost"] - 5.0) < 0.001
    assert abs(rep["lots"][1]["cost"] - 5.5) < 0.001


def test_reduce_position_writes_with_correct_pnl(isolated_db):
    """减仓后reduce行pnl_pct = (reduce_price - lot_cost) / lot_cost * 100."""
    parent = add_buy(code="T_PNL", strategy="mid", price=10.0, quantity=500)
    new_id = reduce_position(parent, 12.0, 200, "partial_take_profit")

    from a_stock.a_screen.decision_log import get
    row = get(new_id)
    assert row["action"] == "reduce"
    assert row["parent_id"] == parent
    assert row["quantity"] == 200
    assert abs(row["pnl_pct"] - 20.0) < 0.001  # (12-10)/10 = 20%
    assert row["close_reason"] == "partial_take_profit"
