"""risk_metrics 单元测试. T_ 前缀测试数据, 不碰真实持仓.
重点测 P1: Sortino 真实现 + 板块集中度/压力测试."""
import math
from a_stock.risk_metrics import (
    compute, classify_sector, sector_concentration, stress_test,
    _portfolio_returns,
)


def _pos(code, name, mv, vol=0.3):
    """造测试持仓."""
    return {"code": code, "name": name, "qty": 1, "price": mv, "mv": mv, "vol": vol}


# === Sortino 真实现 (修 FIXME) ===

def test_sortino_differs_from_sharpe_when_returns():
    """有收益序列时, Sortino 应不同于 Sharpe (下行波动≠总波动)."""
    positions = [_pos("T_001", "T1", 100, 0.3)]
    returns = [0.01, -0.02, 0.015, -0.03, 0.02, -0.01]  # 有负收益
    r = compute(positions, cash=0, returns_by_code={"T_001": returns})
    # 有负收益 → 下行波动>0 → Sortino 有限且与 Sharpe 不同
    assert r["sortino"] != r["sharpe"] or r["sortino"] == 0
    assert "sortino" in r


def test_sortino_none_when_no_downside():
    """全正收益 → 无下行风险 → Sortino 应为 inf 或特殊标记."""
    positions = [_pos("T_001", "T1", 100, 0.3)]
    returns = [0.01, 0.02, 0.015, 0.005]  # 全正
    r = compute(positions, cash=0, returns_by_code={"T_001": returns})
    # 全正无下行波动, Sortino 应很大/inf 或 0 (实现定)
    assert r["sortino"] == float("inf") or r["sortino"] >= r["sharpe"]


def test_sortino_falls_back_when_no_returns_data():
    """无收益序列 → Sortino 降级为 Sharpe (兼容旧调用)."""
    positions = [_pos("T_001", "T1", 100, 0.3)]
    r = compute(positions, cash=0)
    assert r["sortino"] == r["sharpe"]  # 降级, 不崩


# === 板块分类 ===

def test_classify_sector_etf_consumer():
    assert classify_sector("515650", "消费50ETF") == "消费"


def test_classify_sector_chip_etf():
    assert classify_sector("159801", "芯片ETF") == "科技"


def test_classify_sector_gem_etf():
    assert classify_sector("159915", "创业板ETF") == "宽基"


def test_classify_sector_pharma_stock():
    assert classify_sector("600276", "恒瑞医药") == "医药"


def test_classify_sector_liquor_stock():
    assert classify_sector("000858", "五粮液") == "消费"


def test_classify_sector_finance_stock():
    assert classify_sector("300059", "东方财富") == "金融"


def test_classify_sector_unknown():
    assert classify_sector("T_999", "UNKNOWN") == "其他"


# === 板块集中度 ===

def test_sector_concentration_sums_to_100():
    positions = [
        _pos("515650", "消费50ETF", 100),
        _pos("600276", "恒瑞医药", 50),
        _pos("159801", "芯片ETF", 80),
    ]
    sc = sector_concentration(positions)
    total = sum(v for v in sc.values())
    assert abs(total - 100.0) < 0.1, f"板块占比应和≈100, got {total}"


def test_sector_concentration_groups_correctly():
    positions = [
        _pos("515650", "消费50ETF", 100),   # 消费
        _pos("000858", "五粮液", 50),        # 消费
        _pos("600276", "恒瑞医药", 80),      # 医药
    ]
    sc = sector_concentration(positions)
    # 消费 = 100+50 = 150, 医药 = 80, 总 230
    assert abs(sc["消费"] - 150/230*100) < 0.1
    assert abs(sc["医药"] - 80/230*100) < 0.1


# === 压力测试 ===

def test_stress_test_returns_loss_per_scenario():
    positions = [
        _pos("515650", "消费50ETF", 100),   # 消费
        _pos("600276", "恒瑞医药", 80),      # 医药
    ]
    scenarios = stress_test(positions, total=180)
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 1
    for s in scenarios:
        assert "name" in s and "loss" in s and "loss_pct" in s


def test_stress_test_sector_shock_hits_concentrated_sector():
    """板块冲击场景: 该板块持仓越重, 损失越大."""
    positions_concentrated = [
        _pos("515650", "消费50ETF", 200),  # 消费重仓
        _pos("600276", "恒瑞医药", 10),
    ]
    positions_balanced = [
        _pos("515650", "消费50ETF", 100),
        _pos("600276", "恒瑞医药", 110),
    ]
    # 消费跌10%场景
    s_c = stress_test(positions_concentrated, total=210,
                      sector_shocks={"消费": -0.10})
    s_b = stress_test(positions_balanced, total=210,
                      sector_shocks={"消费": -0.10})
    loss_c = [s for s in s_c if "消费" in s["name"]][0]["loss"]
    loss_b = [s for s in s_b if "消费" in s["name"]][0]["loss"]
    assert loss_c > loss_b, "消费重仓应损失更大"


def test_stress_test_market_crash_scenario():
    """全市场暴跌场景: 所有板块同跌, 损失接近总市值×跌幅."""
    positions = [_pos("515650", "消费50ETF", 100),
                 _pos("600276", "恒瑞医药", 100)]
    scenarios = stress_test(positions, total=200, market_crash=-0.08)
    crash = [s for s in scenarios if "暴跌" in s["name"] or "全市场" in s["name"]]
    assert crash, "应有全市场暴跌场景"
    # 损失 ≈ 200 × 8% = 16
    assert 10 < crash[0]["loss"] < 20


# === _portfolio_returns (组合收益序列聚合) ===

def test_portfolio_returns_weights_by_mv():
    """组合收益 = 各标的收益按市值加权."""
    returns_by_code = {
        "T_001": [0.01, 0.02],   # mv 100
        "T_002": [0.04, 0.08],   # mv 100 → 权重各 50%
    }
    positions = [_pos("T_001", "T1", 100), _pos("T_002", "T2", 100)]
    pr = _portfolio_returns(positions, returns_by_code)
    # 加权: (0.01+0.04)/2, (0.02+0.08)/2
    assert abs(pr[0] - 0.025) < 1e-6
    assert abs(pr[1] - 0.05) < 1e-6


def test_portfolio_returns_handles_missing_code():
    """returns_by_code 缺某 code → 该标的视为 0 收益 (不崩)."""
    returns_by_code = {"T_001": [0.01, 0.02]}
    positions = [_pos("T_001", "T1", 100), _pos("T_002", "T2", 100)]
    pr = _portfolio_returns(positions, returns_by_code)
    # T_002 缺 → 0 收益, 权重 50%
    # [0.01*0.5 + 0, 0.02*0.5 + 0]
    assert abs(pr[0] - 0.005) < 1e-6
    assert abs(pr[1] - 0.01) < 1e-6


# === _load_positions net reduce (bugfix: 之前只 sum buy/add, 没减 reduce) ===

def test_load_positions_nets_reduces(tmp_path, monkeypatch):
    """_load_positions 必须减去 reduce 数量. buy 1000 - reduce 600 = 400."""
    import a_stock.config as cfg
    import a_stock.db as db
    from a_stock.risk_metrics import _load_positions
    from a_stock.a_screen.decision_log import reduce_position

    tmp_db = tmp_path / "t_decisions.sqlite"
    monkeypatch.setattr(cfg, "DECISIONS_DB", tmp_db)
    db.init_decisions_db()

    pid = db.insert_decision(code="T_RISK1", name="T测试", strategy="mid",
                             action="buy", decision_date="2026-06-29",
                             price=1.0, quantity=1000)
    reduce_position(pid, reduce_price=1.1, reduce_qty=600, reason="partial_take_profit")
    monkeypatch.setattr("a_stock.risk_metrics._live_price", lambda c: 1.0)

    positions = _load_positions()
    pos = [p for p in positions if p["code"] == "T_RISK1"][0]
    assert pos["qty"] == 400, f"期望 400 (1000-600), 实际 {pos['qty']}"


# === 成本基 + unrealized_pnl (06-29教训: 报盈亏前必查真实成本) ===

def test_load_positions_has_cost_and_unrealized_pnl(tmp_path, monkeypatch):
    """_load_positions 返回 cost (父lot价) 和 unrealized_pnl."""
    import a_stock.config as cfg
    import a_stock.db as db
    from a_stock.risk_metrics import _load_positions
    from a_stock.a_screen.decision_log import reduce_position

    tmp_db = tmp_path / "t_decisions.sqlite"
    monkeypatch.setattr(cfg, "DECISIONS_DB", tmp_db)
    db.init_decisions_db()

    pid = db.insert_decision(code="T_COST1", name="T成本", strategy="mid",
                             action="buy", decision_date="2026-06-29",
                             price=10.0, quantity=100)
    reduce_position(pid, reduce_price=11.0, reduce_qty=40, reason="partial_take_profit")
    monkeypatch.setattr("a_stock.risk_metrics._live_price", lambda c: 12.0)

    positions = _load_positions()
    pos = [p for p in positions if p["code"] == "T_COST1"][0]
    assert pos["qty"] == 60  # 100-40
    assert pos["cost"] == 10.0  # 父lot价, 减仓不改成本
    # 浮盈 = (12 - 10) * 60 = 120
    assert abs(pos["unrealized_pnl"] - 120.0) < 1e-6


def test_load_positions_multi_lot_weighted_cost(tmp_path, monkeypatch):
    """多 lot 取移动加权平均成本: 100@10 + 100@12 → 成本 11."""
    import a_stock.config as cfg
    import a_stock.db as db
    from a_stock.risk_metrics import _load_positions

    tmp_db = tmp_path / "t_decisions.sqlite"
    monkeypatch.setattr(cfg, "DECISIONS_DB", tmp_db)
    db.init_decisions_db()
    db.insert_decision(code="T_COST2", name="T多lot", strategy="mid",
                       action="buy", decision_date="2026-06-29",
                       price=10.0, quantity=100)
    db.insert_decision(code="T_COST2", name="T多lot", strategy="mid",
                       action="add", decision_date="2026-06-29",
                       price=12.0, quantity=100)
    monkeypatch.setattr("a_stock.risk_metrics._live_price", lambda c: 11.0)

    positions = _load_positions()
    pos = [p for p in positions if p["code"] == "T_COST2"][0]
    assert pos["qty"] == 200
    assert abs(pos["cost"] - 11.0) < 1e-6  # (100*10+100*12)/200


# === reduce 标签一致性校验 ===

def test_check_reduce_label_flags_take_profit_with_loss(tmp_path, monkeypatch):
    """partial_take_profit 但 pnl<0 → 标记异常."""
    import a_stock.config as cfg
    import a_stock.db as db
    from a_stock.risk_metrics import check_reduce_label_consistency
    from a_stock.a_screen.decision_log import reduce_position

    tmp_db = tmp_path / "t_decisions.sqlite"
    monkeypatch.setattr(cfg, "DECISIONS_DB", tmp_db)
    db.init_decisions_db()

    pid = db.insert_decision(code="T_LBL1", name="T标签", strategy="mid",
                             action="buy", decision_date="2026-06-29",
                             price=10.0, quantity=100)
    reduce_position(pid, reduce_price=9.0, reduce_qty=50, reason="partial_take_profit")  # 亏却标止盈

    anomalies = check_reduce_label_consistency()
    assert len(anomalies) == 1
    assert anomalies[0]["code"] == "T_LBL1"


def test_check_reduce_label_clean_when_consistent(tmp_path, monkeypatch):
    """标签与pnl一致 → 无异常."""
    import a_stock.config as cfg
    import a_stock.db as db
    from a_stock.risk_metrics import check_reduce_label_consistency
    from a_stock.a_screen.decision_log import reduce_position

    tmp_db = tmp_path / "t_decisions.sqlite"
    monkeypatch.setattr(cfg, "DECISIONS_DB", tmp_db)
    db.init_decisions_db()

    pid = db.insert_decision(code="T_LBL2", name="T标签", strategy="mid",
                             action="buy", decision_date="2026-06-29",
                             price=10.0, quantity=100)
    reduce_position(pid, reduce_price=11.0, reduce_qty=50, reason="partial_take_profit")  # 盈+止盈, 一致

    assert check_reduce_label_consistency() == []
