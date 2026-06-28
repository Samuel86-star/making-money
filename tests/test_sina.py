"""sina.py 数据源单元测试. T_ 前缀不碰真实数据.
重点测全市场资金流备用源 (ssl_bkzj_ssggzj) 字段映射对齐 screener."""
import json
from unittest.mock import patch, MagicMock
from a_stock.a_stock_data.sina import fetch_market_fund_flow_rank


# 模拟新浪返回 (真实字段结构, 已按 netamount 降序 — 与真实接口一致)
_SINA_SAMPLE = [
    {"symbol": "sz000725", "name": "京东方Ａ", "trade": "7.8000",
     "changeratio": "0.037234", "netamount": "3540905484.97",
     "inamount": "19122394887.89", "outamount": "15581489402.92"},
    {"symbol": "sz001399", "name": "N惠科", "trade": "42.0000",
     "changeratio": "3.1502", "netamount": "3216362093.86",
     "inamount": "0", "outamount": "0"},
    {"symbol": "sh600276", "name": "恒瑞医药", "trade": "48.6700",
     "changeratio": "-0.0123", "netamount": "-123456789.00",
     "inamount": "500000000.00", "outamount": "623456789.00"},
]


def _mock_response(data):
    r = MagicMock()
    r.text = json.dumps(data)
    r.raise_for_status = MagicMock()
    return r


def test_fetch_returns_list():
    with patch("a_stock.a_stock_data.sina.em_get", return_value=_mock_response(_SINA_SAMPLE)):
        stocks = fetch_market_fund_flow_rank(top_n=20)
    assert isinstance(stocks, list)
    assert len(stocks) == 3


def test_field_mapping_code_strips_market_prefix():
    """symbol 'sz000725' → code '000725'."""
    with patch("a_stock.a_stock_data.sina.em_get", return_value=_mock_response(_SINA_SAMPLE)):
        stocks = fetch_market_fund_flow_rank(top_n=20)
    assert stocks[0]["code"] == "000725"
    assert stocks[1]["code"] == "001399"
    assert stocks[2]["code"] == "600276"


def test_field_mapping_name_price():
    with patch("a_stock.a_stock_data.sina.em_get", return_value=_mock_response(_SINA_SAMPLE)):
        stocks = fetch_market_fund_flow_rank(top_n=20)
    assert stocks[0]["name"] == "京东方Ａ"
    assert stocks[0]["price"] == 7.80


def test_change_pct_converted_to_percent():
    """changeratio '0.037234' → change_pct 3.72 (%)."""
    with patch("a_stock.a_stock_data.sina.em_get", return_value=_mock_response(_SINA_SAMPLE)):
        stocks = fetch_market_fund_flow_rank(top_n=20)
    assert abs(stocks[0]["change_pct"] - 3.72) < 0.01


def test_negative_change_pct():
    """负涨跌: -0.0123 → -1.23%."""
    with patch("a_stock.a_stock_data.sina.em_get", return_value=_mock_response(_SINA_SAMPLE)):
        stocks = fetch_market_fund_flow_rank(top_n=20)
    assert abs(stocks[2]["change_pct"] - (-1.23)) < 0.01


def test_net_flow_in_yuan():
    """netamount 已是元, 直取 float."""
    with patch("a_stock.a_stock_data.sina.em_get", return_value=_mock_response(_SINA_SAMPLE)):
        stocks = fetch_market_fund_flow_rank(top_n=20)
    assert stocks[0]["net_flow"] == 3540905484.97
    assert stocks[2]["net_flow"] == -123456789.00


def test_inflow_outflow_mapped():
    with patch("a_stock.a_stock_data.sina.em_get", return_value=_mock_response(_SINA_SAMPLE)):
        stocks = fetch_market_fund_flow_rank(top_n=20)
    assert stocks[0]["inflow"] == 19122394887.89
    assert stocks[0]["outflow"] == 15581489402.92


def test_handles_zero_string_fields():
    """'0' 字符串 → 0.0 (不崩)."""
    with patch("a_stock.a_stock_data.sina.em_get", return_value=_mock_response(_SINA_SAMPLE)):
        stocks = fetch_market_fund_flow_rank(top_n=20)
    # N惠科 inamount/outflow='0'
    n_hk = [s for s in stocks if s["code"] == "001399"][0]
    assert n_hk["inflow"] == 0.0
    assert n_hk["outflow"] == 0.0


def test_top_n_limits_result_count():
    """top_n 截断返回数."""
    with patch("a_stock.a_stock_data.sina.em_get", return_value=_mock_response(_SINA_SAMPLE)):
        stocks = fetch_market_fund_flow_rank(top_n=2)
    assert len(stocks) == 2


def test_empty_response_returns_empty_list():
    with patch("a_stock.a_stock_data.sina.em_get", return_value=_mock_response([])):
        stocks = fetch_market_fund_flow_rank(top_n=20)
    assert stocks == []


def test_request_exception_returns_empty():
    """网络异常返回空 list, 不崩 (供降级链判断)."""
    with patch("a_stock.a_stock_data.sina.em_get", side_effect=Exception("SSL error")):
        stocks = fetch_market_fund_flow_rank(top_n=20)
    assert stocks == []


def test_sorted_by_net_flow_desc():
    """返回应按 net_flow 降序 (新浪已按 netamount 排序, 二次保险)."""
    with patch("a_stock.a_stock_data.sina.em_get", return_value=_mock_response(_SINA_SAMPLE)):
        stocks = fetch_market_fund_flow_rank(top_n=20)
    net_flows = [s["net_flow"] for s in stocks]
    assert net_flows == sorted(net_flows, reverse=True)


def test_filters_non_a_stock_etf_bond():
    """排除 5(基金/ETF)/1(债券) 开头, 只留 A 股个股."""
    sample = _SINA_SAMPLE + [
        {"symbol": "sh511270", "name": False, "trade": "120", "changeratio": "0",
         "netamount": "9999999999", "inamount": "0", "outamount": "0"},  # 债券ETF
        {"symbol": "sh515880", "name": "通信ETF", "trade": "1.5", "changeratio": "0.01",
         "netamount": "8888888888", "inamount": "0", "outamount": "0"},  # ETF
    ]
    with patch("a_stock.a_stock_data.sina.em_get", return_value=_mock_response(sample)):
        stocks = fetch_market_fund_flow_rank(top_n=20)
    codes = [s["code"] for s in stocks]
    assert "511270" not in codes, "债券ETF应过滤"
    assert "515880" not in codes, "通信ETF应过滤"
    assert "000725" in codes


def test_falsy_name_fallback_to_code():
    """name 为 False/None/空 → 用 code 兜底."""
    sample = [
        {"symbol": "sz000725", "name": False, "trade": "7.8", "changeratio": "0",
         "netamount": "100", "inamount": "0", "outamount": "0"},
        {"symbol": "sh600276", "name": None, "trade": "48", "changeratio": "0",
         "netamount": "90", "inamount": "0", "outflow": "0", "outamount": "0"},
    ]
    with patch("a_stock.a_stock_data.sina.em_get", return_value=_mock_response(sample)):
        stocks = fetch_market_fund_flow_rank(top_n=20)
    assert stocks[0]["name"] == "000725"
    assert stocks[1]["name"] == "600276"

