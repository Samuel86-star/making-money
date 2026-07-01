"""position_sizer 单元测试.
重点: R倍数输出 (Van Tharp) + 凯利/固定风险 sizing 不回归."""
from a_stock import position_sizer as ps


def _candidate(price=10.0, stop=9.0, target=13.0, win_rate=0.55):
    return ps.Candidate("T_R1", "测试标的", price, target, stop, vol_annual=0.3, win_rate=win_rate)


# === R 倍数输出 (Van Tharp, 07-01 学习路径 P1) ===

def test_r_multiple_fields_present():
    """suggest 输出含 risk_per_share/reward_per_share/R_multiple."""
    r = ps.suggest(_candidate(), 100000, method="fixed")
    assert "risk_per_share" in r
    assert "reward_per_share" in r
    assert "R_multiple" in r


def test_r_multiple_is_reward_over_risk():
    """R_multiple = reward_per_share / risk_per_share ( payoff )."""
    # entry 10, stop 9 → risk 1.0; target 13 → reward 3.0 → R=3.0
    r = ps.suggest(_candidate(price=10.0, stop=9.0, target=13.0), 100000, method="fixed")
    assert r["risk_per_share"] == 1.0
    assert r["reward_per_share"] == 3.0
    assert r["R_multiple"] == 3.0


def test_fixed_method_rationale_speaks_r():
    """fixed 方法 rationale 含 'R' 语言."""
    r = ps.suggest(_candidate(), 100000, method="fixed")
    assert "R" in r["rationale"]


def test_fixed_sizing_risk_pct_of_capital():
    """fixed = 风险1%/止损10% → 仓位10% (1R=1%资本)."""
    # entry 10, stop 9 → stop_pct=10%; risk=1% → frac=0.10
    r = ps.suggest(_candidate(price=10.0, stop=9.0, target=13.0), 100000,
                   method="fixed", risk_per_trade=0.01)
    assert r["suggested_frac"] <= 0.10 + 0.001  # 评分缩放前 (无score=满scale)


def test_kelly_method_unaffected_by_r_fields():
    """kelly 方法仍工作, 且含 R 字段."""
    r = ps.suggest(_candidate(), 100000, method="kelly")
    assert r["method"] == "kelly"
    assert r["R_multiple"] >= 0


def test_shares_rounded_to_100_lot():
    """A股100股整手: shares % 100 == 0."""
    r = ps.suggest(_candidate(price=10.0, stop=9.0, target=13.0), 100000, method="fixed")
    assert r["shares"] % 100 == 0


def test_negative_risk_clamped():
    """止损高于入场 (stop>price) → shares=0, R 多数为负或零."""
    r = ps.suggest(_candidate(price=10.0, stop=11.0, target=13.0), 100000, method="fixed")
    assert r["shares"] == 0
