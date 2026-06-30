"""Portfolio Heat / VCP / Market Regime 三方法论测试.
对应 docs/references/trading-skills-methodology.md 第1/4/5条."""
import a_stock.ohlcv as ohlcv


# === Portfolio Heat (risk_metrics.portfolio_heat) ===

def test_portfolio_heat_basic(monkeypatch):
    """heat = Σ (成本-止损)×持仓. 止损取plan_stop_loss."""
    import a_stock.risk_metrics as rm
    positions = [
        {"code": "T_H1", "name": "测试A", "qty": 100, "cost": 10.0, "mv": 1000.0, "price": 10.0},
        {"code": "T_H2", "name": "测试B", "qty": 200, "cost": 5.0, "mv": 1100.0, "price": 5.5},
    ]
    # mock stop lookup: T_H1 stop=9.0, T_H2 stop=4.5
    monkeypatch.setattr(rm, "_stop_for", lambda code, cost, name: (9.0 if code == "T_H1" else 4.5))
    h = rm.portfolio_heat(positions, total=10000.0)
    # T_H1: (10-9)*100=100, T_H2: (5-4.5)*200=100 → heat=200, 2%
    assert abs(h["heat"] - 200.0) < 1e-6
    assert abs(h["heat_pct"] - 2.0) < 1e-6
    assert h["breach"] is False  # 2% < 6%


def test_portfolio_heat_breach(monkeypatch):
    """heat超6% → breach=True."""
    import a_stock.risk_metrics as rm
    positions = [{"code": "T_HB", "name": "测", "qty": 1000, "cost": 10.0, "mv": 10000.0, "price": 10.0}]
    monkeypatch.setattr(rm, "_stop_for", lambda code, cost, name: 8.0)  # (10-8)*1000=2000
    h = rm.portfolio_heat(positions, total=20000.0)  # 2000/20000=10% > 6%
    assert h["breach"] is True


def test_portfolio_heat_no_stop_uses_atr(monkeypatch):
    """无plan_stop_loss → 用ATR结构止损 (mock)."""
    import a_stock.risk_metrics as rm
    positions = [{"code": "T_HN", "name": "测", "qty": 100, "cost": 10.0, "mv": 1000.0, "price": 10.0}]
    # _stop_for 内部: plan_stop_loss=None → 调 struct_stop_loss
    monkeypatch.setattr(rm, "_stop_for", lambda code, cost, name: 9.5)
    h = rm.portfolio_heat(positions, total=5000.0)
    assert h["heat"] == 50.0  # (10-9.5)*100


# === VCP (ohlcv.vcp_score) ===

def test_vcp_score_contracting_high(monkeypatch):
    """连续波动收缩+量缩 → 高分."""
    import pandas as pd
    # 造60根bar, 4段波动递减, 量递减
    rows = []
    base = 10.0
    vols = [0.08, 0.06, 0.04, 0.02]  # 每段波动幅度递减
    seg_vols = [1000, 800, 600, 400]  # 量递减
    for seg in range(4):
        for i in range(15):
            hi = base * (1 + vols[seg] / 2)
            lo = base * (1 - vols[seg] / 2)
            rows.append({"open": base, "close": base, "high": hi, "low": lo, "volume": seg_vols[seg], "date": f"2026-01-{seg*15+i+1:02d}"})
    df = pd.DataFrame(rows)
    df.index.name = "Date"
    monkeypatch.setattr(ohlcv, "load_ohlcv", lambda code: df)
    score = ohlcv.vcp_score("T_VCP")
    assert score >= 70  # 完美收缩应高分


def test_vcp_score_expanding_low(monkeypatch):
    """波动扩张+量增 → 低分."""
    import pandas as pd
    rows = []
    base = 10.0
    vols = [0.02, 0.04, 0.06, 0.08]  # 波动递增
    seg_vols = [400, 600, 800, 1000]
    for seg in range(4):
        for i in range(15):
            hi = base * (1 + vols[seg] / 2)
            lo = base * (1 - vols[seg] / 2)
            rows.append({"open": base, "close": base, "high": hi, "low": lo, "volume": seg_vols[seg], "date": f"2026-01-{seg*15+i+1:02d}"})
    df = pd.DataFrame(rows)
    df.index.name = "Date"
    monkeypatch.setattr(ohlcv, "load_ohlcv", lambda code: df)
    score = ohlcv.vcp_score("T_EXP")
    assert score < 40


def test_vcp_score_no_data(monkeypatch):
    """无数据返回0."""
    monkeypatch.setattr(ohlcv, "load_ohlcv", lambda code: None)
    assert ohlcv.vcp_score("T_NONE") == 0


# === Market Regime (market_regime.distribution_days / ftd / regime) ===

def test_distribution_days_count(monkeypatch):
    """收盘跌≥0.2%且放量 = 派发日."""
    import a_stock.market_regime as mr
    import pandas as pd
    # 造10根: 第3,5,7天跌≥0.2%且放量
    rows = [
        # date, close, vol
        {"close": 10.0, "high": 10.2, "low": 9.9, "volume": 100, "date": "2026-01-01"},
        {"close": 9.95, "high": 10.1, "low": 9.9, "volume": 90},   # 跌0.5% 但缩量 → 不计
        {"close": 9.90, "high": 10.0, "low": 9.8, "volume": 120},  # 跌0.5% 放量 → 派发
        {"close": 10.0, "high": 10.1, "low": 9.9, "volume": 100},
        {"close": 9.85, "high": 10.0, "low": 9.8, "volume": 130},  # 跌1.5% 放量 → 派发
        {"close": 9.95, "high": 10.0, "low": 9.8, "volume": 110},
        {"close": 9.80, "high": 9.95, "low": 9.7, "volume": 140},  # 跌1.5% 放量 → 派发
        {"close": 9.90, "high": 10.0, "low": 9.8, "volume": 100},
        {"close": 10.0, "high": 10.1, "low": 9.9, "volume": 100},
        {"close": 10.1, "high": 10.2, "low": 10.0, "volume": 100},
    ]
    df = pd.DataFrame(rows)
    df.index.name = "Date"
    monkeypatch.setattr(mr, "load_ohlcv", lambda code: df)
    dd = mr.distribution_days("T_DD")
    assert dd["count"] == 3


def test_regime_levels():
    """派发日计数 → 风险等级."""
    import a_stock.market_regime as mr
    assert mr.regime_from_count(0) == "NORMAL"
    assert mr.regime_from_count(2) == "CAUTION"
    assert mr.regime_from_count(4) == "HIGH"
    assert mr.regime_from_count(6) == "SEVERE"


def test_ftd_signal(monkeypatch):
    """跌势后第4-7天放量涨≥1.5% = FTD."""
    import a_stock.market_regime as mr
    import pandas as pd
    # 前5天下跌, 第6天(第5日跌势后)放量涨2%
    rows = []
    px = 10.0
    for i in range(5):
        px *= 0.98
        rows.append({"close": px, "high": px*1.01, "low": px*0.99, "volume": 100})
    # 第6天放量涨2%
    rows.append({"close": px*1.02, "high": px*1.03, "low": px*0.99, "volume": 200})
    df = pd.DataFrame(rows)
    df.index.name = "Date"
    monkeypatch.setattr(mr, "load_ohlcv", lambda code: df)
    ftd = mr.ftd_signal("T_FTD")
    assert ftd is not None
    assert ftd["pct"] >= 1.5
