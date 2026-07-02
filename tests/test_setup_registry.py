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


# === load_registry / detect_setup ===

from a_stock.setup_registry import load_registry, detect_setup, SETUP_FNS


def test_load_registry_from_json(tmp_path, monkeypatch):
    """加载最新日期目录的setup_registry.json."""
    import json
    import a_stock.config as cfg
    d = tmp_path / "2026-07-02"
    d.mkdir()
    json.dump({"registry": [
        {"setup": "Turtle sys1", "win_rate": 0.423, "payoff": 2.04, "expectancy": 0.012}],
        "stop_pct": 0.05}, open(d / "setup_registry.json", "w"))
    monkeypatch.setattr(cfg, "DAILY_DIR", tmp_path)
    reg = load_registry()
    assert "Turtle sys1" in reg
    assert reg["Turtle sys1"]["win_rate"] == 0.423


def test_load_registry_missing_returns_empty(tmp_path, monkeypatch):
    """无文件 → {} (不崩)."""
    import a_stock.config as cfg
    monkeypatch.setattr(cfg, "DAILY_DIR", tmp_path)
    assert load_registry() == {}


def test_load_registry_picks_latest_date(tmp_path, monkeypatch):
    """多日期目录 → 取最新."""
    import json
    import a_stock.config as cfg
    for dt, val in [("2026-07-01", 0.5), ("2026-07-02", 0.7)]:
        d = tmp_path / dt
        d.mkdir()
        json.dump({"registry": [{"setup": "X", "win_rate": val, "payoff": 1.5,
                                 "expectancy": 0.01}]},
                  open(d / "setup_registry.json", "w"))
    monkeypatch.setattr(cfg, "DAILY_DIR", tmp_path)
    assert load_registry()["X"]["win_rate"] == 0.7  # 取最新07-02


def test_detect_setup_returns_highest_expectancy_match(monkeypatch):
    """detect_setup: 命中多setup时, 返回registry中期望最高的."""
    import a_stock.config as cfg
    import a_stock.ohlcv as ohlcv
    import pandas as pd
    # 假data: 够长, 所有signal_fn都返回True (靠mock SETUP_FNS)
    monkeypatch.setattr(ohlcv, "load_ohlcv",
                        lambda c: pd.DataFrame({"close": [10.0]*100, "volume": [1000]*100}))
    # mock SETUP_FNS 全True
    import a_stock.setup_registry as sr
    monkeypatch.setattr(sr, "SETUP_FNS", {
        "强setup": lambda c, v: True,
        "弱setup": lambda c, v: True,
    })
    reg = {"强setup": {"expectancy": 0.02, "win_rate": 0.5, "payoff": 2},
           "弱setup": {"expectancy": 0.005, "win_rate": 0.4, "payoff": 1.5}}
    setup = detect_setup("T_X", registry=reg)
    assert setup == "强setup"


def test_detect_setup_none_when_no_signal(monkeypatch):
    """无信号命中 → None."""
    import a_stock.ohlcv as ohlcv
    import pandas as pd
    import a_stock.setup_registry as sr
    monkeypatch.setattr(ohlcv, "load_ohlcv",
                        lambda c: pd.DataFrame({"close": [10.0]*100, "volume": [1000]*100}))
    monkeypatch.setattr(sr, "SETUP_FNS", {"X": lambda c, v: False})
    assert detect_setup("T_Y", registry={"X": {"expectancy": 0.02}}) is None
