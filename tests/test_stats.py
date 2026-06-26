"""Tests for stats.py: overall, strategy, code, discipline queries."""
import py.db as db
import py.a_screen.decision_log as dl
import py.stats as stats


def setup_function(_):
    db.init_decisions_db()


def test_stats_overall():
    for i, (price, close, reason) in enumerate([
        (10, 11, "target"), (10, 9, "stop_loss"), (10, 12, "target"),
        (10, 9.5, "manual"), (10, 11.5, "expired"),
    ]):
        id_ = dl.add_buy(code=f"00000{i}", strategy="short", price=price, quantity=100)
        dl.close(id_, "2026-07-01", close, reason)

    s = stats.compute_overall()
    assert s["total"] == 5
    assert 0 <= s["win_rate"] <= 1
    assert 0 <= s["discipline_rate"] <= 1


def test_stats_by_strategy():
    for code in ["A", "B"]:
        id_ = dl.add_buy(code=code, strategy="mid", price=10, quantity=100)
        dl.close(id_, "2026-07-01", 11, "target")
    s = stats.compute_by_strategy("mid")
    assert s["total"] == 2
    assert s["win_rate"] == 1.0