from py.a_screen.candidate_filter import initial_filter


def test_short_filter_picks_1_to_7_pct_gain():
    stocks = [
        {"code": "A", "change_pct": 0.5, "net_flow": 1e7},
        {"code": "B", "change_pct": 3.0, "net_flow": 2e7},
        {"code": "C", "change_pct": 8.0, "net_flow": 5e7},
        {"code": "D", "change_pct": 2.0, "net_flow": -1e6},
    ]
    out = initial_filter(stocks, "short")
    codes = {s["code"] for s in out}
    assert "A" in codes
    assert "B" in codes
    assert "C" not in codes  # 涨幅过高
    assert "D" not in codes  # 净流出


def test_mid_filter_picks_pe_in_range():
    stocks = [
        {"code": "A", "pe_ttm": 15, "mcap_yi": 100, "fund_flow_20d": 1e8},
        {"code": "B", "pe_ttm": 80, "mcap_yi": 100, "fund_flow_20d": 1e8},
        {"code": "C", "pe_ttm": 25, "mcap_yi": 30,  "fund_flow_20d": 1e8},
    ]
    out = initial_filter(stocks, "mid")
    codes = {s["code"] for s in out}
    assert "A" in codes
    assert "B" not in codes  # PE 过高
    assert "C" not in codes  # 市值过小