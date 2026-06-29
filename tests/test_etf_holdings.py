"""ETF 成分股拉取单元测试. 离线 mock, 不依赖网络."""
import json
from unittest.mock import patch

import a_stock.a_stock_data.etf_holdings as eh
from a_stock.a_stock_data.etf_holdings import (
    Holding, is_north_code, _market_of, get_etf_holdings, has_north_exchange,
)


# 真实行片段 (取自 159915, 简化)
_SAMPLE_HTML = (
    "var apidata={ content=\"<div>...截止至：<font class='px12'>2026-03-31</font>..."
    "<tbody>"
    "<tr><td>1</td><td><a href='//quote.eastmoney.com/unify/r/0.300750'>300750</a></td>"
    "<td class='tol'><a href='//quote.eastmoney.com/unify/r/0.300750'>宁德时代</a></td>"
    "<td class='tor'><span data-id='dq300750'></span></td>"
    "<td class='tor'><span data-id='zd300750'></span></td>"
    "<td class='xglj'>...</td><td class='tor'>19.69%</td>"
    "<td class='tor'>2,501.44</td><td class='tor'>1,004,828.17</td></tr>"
    # 北交所样本 (920xxx)
    "<tr><td>2</td><td><a href='//quote.eastmoney.com/unify/r/0.920111'>920111</a></td>"
    "<td class='tol'><a href='//quote.eastmoney.com/unify/r/0.920111'>北交所样本</a></td>"
    "<td class='tor'>x</td><td class='tor'>x</td><td>x</td>"
    "<td class='tor'>3.21%</td><td>1</td><td>2</td></tr>"
    # 沪市样本
    "<tr><td>3</td><td><a href='//quote.eastmoney.com/unify/r/1.600519'>600519</a></td>"
    "<td class='tol'><a href='//quote.eastmoney.com/unify/r/1.600519'>贵州茅台</a></td>"
    "<td class='tor'>x</td><td class='tor'>x</td><td>x</td>"
    "<td class='tor'>1.50%</td><td>1</td><td>2</td></tr>"
    "</tbody>\"}"
)


# === 北交所代码判定 ===
def test_is_north_code_prefixes():
    assert is_north_code("920111")
    assert is_north_code("830789")
    assert is_north_code("870866")
    assert is_north_code("430047")
    assert not is_north_code("300750")
    assert not is_north_code("600519")
    assert not is_north_code("000001")


# === 市场判定 ===
def test_market_of_north_wins_over_secid():
    # secid 0 但代码是北交所 → bj
    assert _market_of("920111", "0") == "bj"


def test_market_of_sh_by_secid_and_prefix():
    assert _market_of("600519", "1") == "sh"
    assert _market_of("515650", "0") == "sh"  # ETF 5 开头算沪


def test_market_of_sz():
    assert _market_of("300750", "0") == "sz"
    assert _market_of("000001", "0") == "sz"


# === 解析 ===
@patch("a_stock.a_stock_data.etf_holdings.em_cache_get", return_value=None)
@patch("a_stock.a_stock_data.etf_holdings.em_cache_put")
@patch("a_stock.a_stock_data.etf_holdings._fetch_raw", return_value=_SAMPLE_HTML)
def test_get_etf_holdings_parses_rows(_fetch, _put, _get):
    hs = get_etf_holdings("159915")
    assert len(hs) == 3
    assert hs[0] == Holding("300750", "宁德时代", 19.69, "sz")
    assert hs[1].market == "bj"  # 920111
    assert hs[1].code == "920111"
    assert hs[2].market == "sh"  # 600519


@patch("a_stock.a_stock_data.etf_holdings.em_cache_get", return_value=None)
@patch("a_stock.a_stock_data.etf_holdings.em_cache_put")
@patch("a_stock.a_stock_data.etf_holdings._fetch_raw", return_value=_SAMPLE_HTML)
def test_get_etf_holdings_caches_result(_fetch, _put, _get):
    get_etf_holdings("159915")
    assert _put.called
    cached = _put.call_args[0][1]
    # 缓存内容可 round-trip
    assert json.loads(json.dumps(cached))[0]["code"] == "300750"


@patch("a_stock.a_stock_data.etf_holdings.get_etf_holdings")
def test_has_north_exchange_true_when_bj_present(mock_get):
    mock_get.return_value = [Holding("300750", "a", 10, "sz"),
                             Holding("920111", "b", 3, "bj")]
    assert has_north_exchange("159915") is True


@patch("a_stock.a_stock_data.etf_holdings.get_etf_holdings")
def test_has_north_exchange_false_when_none(mock_get):
    mock_get.return_value = [Holding("300750", "a", 10, "sz"),
                             Holding("600519", "b", 3, "sh")]
    assert has_north_exchange("159915") is False


@patch("a_stock.a_stock_data.etf_holdings._fetch_raw", return_value=_SAMPLE_HTML)
def test_get_as_of_date(_fetch):
    assert eh.get_as_of_date("159915") == "2026-03-31"


@patch("a_stock.a_stock_data.etf_holdings._fetch_raw", return_value="garbage")
def test_get_as_of_date_none_when_missing(_fetch):
    assert eh.get_as_of_date("159915") is None


@patch("a_stock.a_stock_data.etf_holdings._fetch_raw", return_value="")
def test_get_etf_holdings_empty_on_no_rows(_fetch):
    # 空响应不应崩, 返回空列表 (cache 空也写)
    with patch("a_stock.a_stock_data.etf_holdings.em_cache_get", return_value=None), \
         patch("a_stock.a_stock_data.etf_holdings.em_cache_put"):
        assert get_etf_holdings("159915") == []
