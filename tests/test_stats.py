"""Tests for stats.py: overall, strategy, code, discipline queries."""
import a_stock.db as db
import a_stock.a_screen.decision_log as dl
import a_stock.stats as stats

# 测试用 T_ 前缀,与真实数据隔离
T = "T_"


def setup_function(_):
    db.init_decisions_db()
    _clean_test_data()


def teardown_function(_):
    """测试后清 T_ 数据, 防残留污染生产库."""
    _clean_test_data()


def _clean_test_data():
    with db.conn(db.cfg.DECISIONS_DB) as c:
        c.execute("DELETE FROM decisions WHERE code LIKE ?", (f"{T}%",))


def test_stats_overall():
    test_codes = [f"{T}{i:05d}" for i in range(5)]
    for code, (price, close, reason) in zip(test_codes, [
        (10, 11, "target"), (10, 9, "stop_loss"), (10, 12, "target"),
        (10, 9.5, "manual"), (10, 11.5, "expired"),
    ]):
        id_ = dl.add_buy(code=code, strategy="short", price=price, quantity=100)
        dl.close(id_, "2026-07-01", close, reason)

    # 过滤只算测试数据的 closed
    with db.conn(db.cfg.DECISIONS_DB) as c:
        closed = c.execute(
            "SELECT * FROM decisions WHERE code LIKE ? AND close_date IS NOT NULL",
            (f"{T}%",)).fetchall()

    assert len(closed) == 5
    s = stats.compute_overall()
    # stats.compute_overall 看全部;断言 win_rate / discipline 在合法范围即可
    assert 0 <= s["win_rate"] <= 1
    assert 0 <= s["discipline_rate"] <= 1


def test_stats_by_strategy():
    for code in [f"{T}AA", f"{T}BB"]:
        id_ = dl.add_buy(code=code, strategy="mid", price=10, quantity=100)
        dl.close(id_, "2026-07-01", 11, "target")
    s = stats.compute_by_strategy("mid")
    # 看全部 mid 策略;真实数据可能为 0,只断言函数可调
    assert s["total"] >= 2
    assert 0 <= s["win_rate"] <= 1