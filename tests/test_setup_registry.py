"""setup_registry 单元测试.
expectancy: returns → win_rate/avg_win/avg_loss/payoff/expectancy/kelly.
建edge库: 验证过的setup → 可sizing的Kelly分数."""
from a_stock.setup_registry import expectancy, kelly_fraction


def test_expectancy_mixed():
    """混合盈亏 → win_rate/avg_win/avg_loss/payoff正确."""
    rets = [0.10, -0.05, 0.03, -0.03]  # 2 win / 2 loss
    e = expectancy(rets)
    assert e["count"] == 4
    assert e["wins"] == 2
    assert abs(e["win_rate"] - 0.5) < 1e-9
    assert abs(e["avg_win"] - 0.065) < 1e-9      # (0.10+0.03)/2
    assert abs(e["avg_loss"] - (-0.04)) < 1e-9    # (-0.05+-0.03)/2
    assert abs(e["payoff"] - 1.625) < 1e-9        # 0.065/0.04
    # expectancy = 0.5*0.065 + 0.5*(-0.04) = 0.0125
    assert abs(e["expectancy"] - 0.0125) < 1e-9


def test_expectancy_all_wins():
    """全盈 → win_rate=1, avg_loss=0 (无亏损样本)."""
    e = expectancy([0.05, 0.10, 0.03])
    assert e["win_rate"] == 1.0
    assert e["avg_loss"] == 0.0
    assert e["avg_win"] > 0


def test_expectancy_all_losses():
    """全亏 → win_rate=0, avg_win=0."""
    e = expectancy([-0.05, -0.03])
    assert e["win_rate"] == 0.0
    assert e["avg_win"] == 0.0
    assert e["avg_loss"] < 0


def test_expectancy_empty():
    """空 → 全None/0, 不崩."""
    e = expectancy([])
    assert e["count"] == 0
    assert e["win_rate"] == 0


def test_kelly_fraction_basic():
    """Kelly: f=(p*b-q)/b, 半Kelly."""
    # win_rate=0.55, payoff=1.5 → f=(0.55*1.5-0.45)/1.5 = (0.825-0.45)/1.5=0.25
    k = kelly_fraction(0.55, 1.5, fraction=1.0)
    assert abs(k - 0.25) < 1e-9
    # 半Kelly
    kh = kelly_fraction(0.55, 1.5, fraction=0.5)
    assert abs(kh - 0.125) < 1e-9


def test_kelly_zero_payoff():
    """payoff=0 → Kelly 0."""
    assert kelly_fraction(0.5, 0) == 0.0


def test_kelly_negative_expectancy():
    """负期望 (win_rate低/payoff低) → Kelly 0 (不交易)."""
    # win_rate=0.3, payoff=1.0 → (0.3-0.7)/1 = -0.4 → max(0)=0
    assert kelly_fraction(0.3, 1.0) == 0.0


def test_kelly_capped():
    """Kelly封顶 (单笔不超过30%)."""
    # 极强: win_rate=0.9, payoff=5 → f=(0.9*5-0.1)/5=0.88 → 半Kelly 0.44 → cap 0.30
    k = kelly_fraction(0.9, 5.0, fraction=0.5, cap=0.30)
    assert k == 0.30


def test_expectancy_uses_stopped_returns():
    """含止损封顶的returns (-stop) 也能算expectancy."""
    # VCP突破型: 多次-5%止损 + 少数大赚
    rets = [-0.05, -0.05, -0.05, 0.20, -0.05, 0.15]
    e = expectancy(rets)
    assert e["win_rate"] < 0.5  # 2/6 win
    assert e["avg_loss"] == -0.05  # 全止损在-5%
    assert e["avg_win"] > 0.15
    # expectancy = (2/6)*0.175 + (4/6)*(-0.05) = 0.0583 - 0.0333 = 0.025
    assert e["expectancy"] > 0  # 正期望 (大赢覆盖多次小亏)
