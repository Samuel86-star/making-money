"""MFE/MAE + Expectancy + backtest hypothesis 三方法论测试.
对应 docs/references/trading-skills-methodology.md 第2/3/6条."""
import json
import a_stock.db as db
import a_stock.a_screen.decision_log as dl
import a_stock.config as cfg

T = "T_"


def setup_function(_):
    db.init_decisions_db()
    _clean()


def teardown_function(_):
    _clean()


def _clean():
    with db.conn(cfg.DECISIONS_DB) as c:
        c.execute(
            "DELETE FROM decisions WHERE code LIKE ? OR parent_id IN "
            "(SELECT id FROM decisions WHERE code LIKE ?)",
            (f"{T}%", f"{T}%"),
        )


# === MFE/MAE (mfe_mae.update / snapshot / report) ===

def test_mfe_mae_init_and_update(monkeypatch, tmp_path):
    """新仓 init, 后续update追踪max/min."""
    import a_stock.mfe_mae as mm
    state = tmp_path / "mfe.json"
    monkeypatch.setattr(mm, "STATE_FILE", state)
    # 建仓 T_MM 100@10
    dl.add_buy(code=f"{T}MM", strategy="mid", price=10.0, quantity=100)
    # 第一次update price=10.5
    mm.update({f"{T}MM": 10.5})
    snap = mm.snapshot(f"{T}MM")
    assert snap["entry"] == 10.0
    assert snap["max_price"] == 10.5
    assert snap["min_price"] == 10.5
    assert abs(snap["mfe_pct"] - 5.0) < 1e-6
    # 跌到 9.5
    mm.update({f"{T}MM": 9.5})
    snap = mm.snapshot(f"{T}MM")
    assert snap["max_price"] == 10.5  # 保留历史高
    assert snap["min_price"] == 9.5
    assert abs(snap["mae_pct"] - 5.0) < 1e-6  # (10-9.5)/10
    assert abs(snap["mfe_pct"] - 5.0) < 1e-6


def test_mfe_mae_closed_position_removed(monkeypatch, tmp_path):
    """平仓后 state 清除."""
    import a_stock.mfe_mae as mm
    state = tmp_path / "mfe.json"
    monkeypatch.setattr(mm, "STATE_FILE", state)
    lot = dl.add_buy(code=f"{T}MC", strategy="mid", price=10.0, quantity=100)
    mm.update({f"{T}MC": 10.5})
    assert mm.snapshot(f"{T}MC") is not None
    # 全平
    dl.reduce_position(lot, 11.0, 100, "target")
    mm.update({f"{T}MC": 11.0})
    assert mm.snapshot(f"{T}MC") is None  # 已无持仓


# === Expectancy (stats.expectancy, 需setup字段) ===

def test_expectancy_by_setup(monkeypatch, tmp_path):
    """按setup分组算 win_rate/avg_win/avg_loss/expectancy."""
    import a_stock.stats as st
    # 迁移加setup列
    db._migrate_setup_column() if hasattr(db, "_migrate_setup_column") else None
    # 造3笔回踩setup: 2盈1亏
    _add_closed(f"{T}E1", "pullback", +10.0)
    _add_closed(f"{T}E2", "pullback", +5.0)
    _add_closed(f"{T}E3", "pullback", -8.0)
    # 1笔突破setup: 亏
    _add_closed(f"{T}E4", "breakout", -3.0)
    exp = st.expectancy(setup="pullback")
    assert exp["n"] == 3
    assert exp["wins"] == 2
    assert exp["losses"] == 1
    assert abs(exp["win_rate"] - 2 / 3) < 1e-3
    # expectancy = (2/3)*7.5 - (1/3)*8 = 5 - 2.667 = 2.333
    assert abs(exp["expectancy_pct"] - (2 / 3 * 7.5 - 1 / 3 * 8)) < 1e-2


def _add_closed(code, setup, pnl_pct):
    """造一笔已平仓 reduce 行带 setup + pnl_pct."""
    lot = dl.add_buy(code=code, strategy="mid", price=10.0, quantity=100)
    rid = dl.reduce_position(lot, 10.0 + pnl_pct / 10, 100, "target" if pnl_pct > 0 else "stop_loss")
    # 写 setup
    with db.conn(cfg.DECISIONS_DB) as c:
        c.execute("UPDATE decisions SET setup=? WHERE id=?", (setup, rid))


# === backtest_hypothesis (backtest_hypothesis.run) ===

def test_backtest_sample_size_warning(monkeypatch, tmp_path):
    """样本<30 → 警告样本不足."""
    import a_stock.backtest_hypothesis as bh
    db._migrate_setup_column() if hasattr(db, "_migrate_setup_column") else None
    _add_closed(f"{T}B1", "pullback", +5.0)
    _add_closed(f"{T}B2", "pullback", -3.0)
    r = bh.run(setup="pullback")
    assert r["n"] == 2
    assert r["sample_adequate"] is False  # <30
    assert "样本不足" in r["warnings"][0] or any("样本" in w for w in r["warnings"])
