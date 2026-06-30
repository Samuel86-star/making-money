"""审计修复测试: setup写入链 + posture择时优先级 (audit 🔴1/🔴2)."""
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


# === 🔴1 setup写入链 ===

def test_add_buy_with_setup():
    rid = dl.add_buy(code=f"{T}SB", strategy="mid", price=10.0, quantity=100, setup="pullback")
    with db.conn(cfg.DECISIONS_DB) as c:
        row = c.execute("SELECT setup FROM decisions WHERE id=?", (rid,)).fetchone()
    assert row["setup"] == "pullback"


def test_add_add_with_setup():
    dl.add_buy(code=f"{T}SA", strategy="mid", price=10.0, quantity=100, setup="breakout")
    rid = dl.add_add(code=f"{T}SA", strategy="mid", price=11.0, quantity=100, setup="breakout")
    with db.conn(cfg.DECISIONS_DB) as c:
        row = c.execute("SELECT setup FROM decisions WHERE id=?", (rid,)).fetchone()
    assert row["setup"] == "breakout"


def test_add_buy_no_setup_defaults_null():
    rid = dl.add_buy(code=f"{T}SN", strategy="mid", price=10.0, quantity=100)
    with db.conn(cfg.DECISIONS_DB) as c:
        row = c.execute("SELECT setup FROM decisions WHERE id=?", (rid,)).fetchone()
    assert row["setup"] is None


def test_expectancy_filters_by_setup():
    """带setup的reduce参与expectancy, 未带setup归未分类."""
    import a_stock.stats as st
    # pullback 2盈1亏
    _closed(f"{T}E1", "pullback", +5.0)
    _closed(f"{T}E2", "pullback", +3.0)
    _closed(f"{T}E3", "pullback", -2.0)
    # breakout 1亏
    _closed(f"{T}E4", "breakout", -4.0)
    pb = st.expectancy(setup="pullback")
    assert pb["n"] == 3 and pb["wins"] == 2
    bo = st.expectancy(setup="breakout")
    assert bo["n"] == 1 and bo["losses"] == 1


def _closed(code, setup, pnl_pct):
    lot = dl.add_buy(code=code, strategy="mid", price=10.0, quantity=100, setup=setup)
    rid = dl.reduce_position(lot, 10.0 + pnl_pct / 10, 100,
                             "target" if pnl_pct > 0 else "stop_loss")
    with db.conn(cfg.DECISIONS_DB) as c:
        c.execute("UPDATE decisions SET setup=? WHERE id=?", (setup, rid))


# === 🔴2 posture择时优先级 ===

def test_posture_normal_offensive():
    from a_stock.market_regime import posture
    assert posture("NORMAL", 50)["posture"] == "offensive"
    assert posture("NORMAL", 10)["posture"] == "offensive"  # NORMAL任何情绪都进攻


def test_posture_caution_split_by_sentiment():
    from a_stock.market_regime import posture
    assert posture("CAUTION", 30)["posture"] == "defensive"  # 冷
    assert posture("CAUTION", 60)["posture"] == "neutral"    # 暖


def test_posture_high_severe_defensive():
    from a_stock.market_regime import posture
    assert posture("HIGH", 50)["posture"] == "defensive"
    assert posture("SEVERE", 50)["posture"] == "defensive"
    assert posture("SEVERE", 80)["posture"] == "defensive"  # 即便情绪暖
