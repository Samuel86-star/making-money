from unittest.mock import patch
from a_stock.a_screen.brief_builder import build_snapshot, render_markdown


def test_build_snapshot_combines_sources():
    with patch("a_stock.a_screen.brief_builder.tencent_quote") as m_t, \
         patch("a_stock.a_screen.brief_builder.eastmoney_concept_blocks") as m_c, \
         patch("a_stock.a_screen.brief_builder.stock_fund_flow_120d") as m_f, \
         patch("a_stock.a_screen.brief_builder.eastmoney_reports") as m_r, \
         patch("a_stock.a_screen.brief_builder.ths_eps_forecast") as m_e:
        m_t.return_value = {"000858": {"name": "五粮液", "price": 168.5, "pe_ttm": 22.5, "pb": 4.8, "mcap_yi": 6543, "industry": "白酒"}}
        m_c.return_value = {"industries": [{"name": "白酒"}], "concepts": [{"name": "消费"}], "regions": []}
        m_f.return_value = [{"date": "2026-06-20", "main": 1e8}]
        m_r.return_value = [{"title": "高端白酒景气", "org": "中信", "rating": "买入", "date": "2026-06-20"}]
        m_e.return_value = [{"year": "2026E", "eps": 8.5, "org_count": 23}]

        snap = build_snapshot("000858", "2026-06-26")

    assert snap["meta"]["code"] == "000858"
    assert snap["fundamentals"]["price"] == 168.5
    assert "白酒" in [i["name"] for i in snap["membership"]["industries"]]
    assert len(snap["research"]["reports"]) == 1


def test_render_markdown_contains_key_sections():
    snap = {
        "meta": {"code": "000858", "name": "五粮液", "generated_at": "2026-06-26T10:00:00", "trigger": "manual"},
        "snapshot_date": "2026-06-26",
        "fundamentals": {
            "price": 168.5, "change_pct": 0.5, "pe_ttm": 22.5, "pb": 4.8,
            "mcap_yi": 6543, "float_mcap_yi": 5000, "industry": "白酒",
            "limit_up": 185.0, "limit_down": 152.0,
        },
        "membership": {"industries": [{"name": "白酒"}], "concepts": [], "regions": []},
        "fund_flow": {"today": {}, "5d_cumulative": 0, "20d_cumulative": 0},
        "research": {"report_count_30d": 0, "reports": []},
        "consensus": {},
        "risks": ["test risk"],
        "ai_analysis": None,
    }
    md = render_markdown(snap)
    assert "五粮液" in md
    assert "000858" in md
    assert "基础面" in md
    assert "AI 跨信号分析" in md