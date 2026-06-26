import a_stock.config as cfg
from a_stock.a_screen.candidate_filter import score_candidate


def test_short_score_in_range():
    c = {"code": "X", "change_pct": 3.0, "net_flow": 1e8,
         "sector_alignment": 0.8, "report_count_7d": 5, "hot_reason_hit": True}
    sector_data = {"industry": [{"name": "白酒", "codes": ["X"]}]}
    s = score_candidate(c, "short", sector_data)
    assert 0 <= s <= 100


def test_mid_score_uses_valuation():
    c = {"code": "X", "pe_ttm": 15, "pb": 2.0, "fund_flow_20d": 1e8,
         "report_count_30d": 10, "theme_catalyst": 0.7, "tech_position": 0.6}
    s = score_candidate(c, "mid", {})
    assert 0 <= s <= 100
    assert s > 50  # 全正面