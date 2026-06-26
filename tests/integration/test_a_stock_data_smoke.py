"""Smoke tests for vendored a-stock-data endpoints (skip by default, need network).

Each test imports the corresponding vendored function and makes a real API call
to verify the endpoint is reachable and returns expected structure.
"""

import pytest

pytestmark = pytest.mark.skip(reason="needs network (real API call)")


def test_tencent_quote():
    """tencent_quote: real-time quotes via qt.gtimg.cn."""
    from a_stock.a_stock_data.tencent import tencent_quote

    result = tencent_quote(["000001", "600519"])
    assert "000001" in result
    assert "600519" in result
    s = result["000001"]
    # Tencent returns ~50+ fields; check a few mandatory ones
    assert "name" in s
    assert "price" in s
    assert s["price"] is not None


def test_industry_comparison():
    """industry_comparison: eastmoney sector ranking."""
    from a_stock.a_stock_data.sectors import industry_comparison

    result = industry_comparison(top_n=5)
    assert "top" in result
    assert "bottom" in result
    assert "total" in result
    assert isinstance(result["total"], int)
    assert result["total"] > 0
    assert len(result["top"]) <= 5


def test_eastmoney_reports():
    """eastmoney_reports: financial report calendar."""
    from a_stock.a_stock_data.eastmoney import eastmoney_reports

    result = eastmoney_reports(code="000001", year=2025)
    assert isinstance(result, list)


def test_eastmoney_industry_reports():
    """eastmoney_industry_reports: industry research reports."""
    from a_stock.a_stock_data.eastmoney import eastmoney_industry_reports

    result = eastmoney_industry_reports("银行", page=1)
    assert isinstance(result, dict)
    assert "list" in result or "data" in result


def test_eastmoney_concept_blocks():
    """eastmoney_concept_blocks: concept block ranking."""
    from a_stock.a_stock_data.eastmoney import eastmoney_concept_blocks

    result = eastmoney_concept_blocks(top_n=5)
    assert isinstance(result, list)


def test_eastmoney_fund_flow_minute():
    """eastmoney_fund_flow_minute: intraday fund flow."""
    from a_stock.a_stock_data.eastmoney import eastmoney_fund_flow_minute

    result = eastmoney_fund_flow_minute("000001")
    assert isinstance(result, list)


def test_stock_fund_flow_120d():
    """stock_fund_flow_120d: 120-day fund flow history."""
    from a_stock.a_stock_data.eastmoney import stock_fund_flow_120d

    result = stock_fund_flow_120d("000001")
    assert isinstance(result, list)


def test_daily_dragon_tiger():
    """daily_dragon_tiger: daily dragon-tiger board data."""
    from a_stock.a_stock_data.eastmoney import daily_dragon_tiger

    result = daily_dragon_tiger(date_str="2026-06-26", top_n=5)
    assert isinstance(result, list)


def test_ths_hot_reason():
    """ths_hot_reason: Tonghuashun hot-reason analysis."""
    from a_stock.a_stock_data.ths import ths_hot_reason

    result = ths_hot_reason("000001")
    assert isinstance(result, dict)
    assert "reason" in result or "hot" in result


def test_ths_eps_forecast():
    """ths_eps_forecast: Tonghuashun earnings forecast."""
    from a_stock.a_stock_data.ths import ths_eps_forecast

    result = ths_eps_forecast("000001")
    assert isinstance(result, list)


def test_hsgt_realtime():
    """hsgt_realtime: north-bound capital flow (沪深港通)."""
    from a_stock.a_stock_data.ths import hsgt_realtime

    result = hsgt_realtime()
    assert isinstance(result, dict) or isinstance(result, list)


def test_eastmoney_stock_news():
    """eastmoney_stock_news: stock-specific news."""
    from a_stock.a_stock_data.news import eastmoney_stock_news

    result = eastmoney_stock_news("000001", page=1)
    assert isinstance(result, list)


def test_eastmoney_global_news():
    """eastmoney_global_news: global market news."""
    from a_stock.a_stock_data.news import eastmoney_global_news

    result = eastmoney_global_news(page=1)
    assert isinstance(result, list)


def test_download_pdf():
    """download_pdf: stub test — requires a real URL to work."""
    from a_stock.a_stock_data.pdf import download_pdf

    # Just verify import succeeded; actual download skipped via pytestmark
    assert callable(download_pdf)


def test_sina_financial_report():
    """sina_financial_report: financial statements from Sina."""
    from a_stock.a_stock_data.financials import sina_financial_report

    result = sina_financial_report("000001")
    assert isinstance(result, list)


def test_cninfo_announcements():
    """cninfo_announcements: listed-company announcements."""
    from a_stock.a_stock_data.filings import cninfo_announcements

    result = cninfo_announcements("000001", page=1)
    assert isinstance(result, list)