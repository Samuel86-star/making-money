"""Test tencent_quote: parsing, retry, empty edge case."""

from unittest.mock import MagicMock, patch

from py.a_stock_data.tencent import tencent_quote


def _mock_resp(text: str):
    m = MagicMock()
    m.read.return_value = text.encode("gbk")
    m.__enter__ = lambda s: s
    m.__exit__ = lambda s, *a: None
    return m


# Build a VALID Tencent response with known field positions.
# Tencent fields: 0=market,1=name,2=code,3=price,4=last_close,5=open,
#                 38=turnover_pct,39=pe_ttm,44=mcap_yi,47=limit_up,48=limit_down
_FIELDS = [""] * 53
_FIELDS[0] = "1"
_FIELDS[1] = "贵州茅台"
_FIELDS[2] = "600519"
_FIELDS[3] = "1685.00"
_FIELDS[4] = "1670.00"
_FIELDS[5] = "1690.00"
_FIELDS[38] = "3.2"
_FIELDS[39] = "22.5"
_FIELDS[44] = "65432.1"
_FIELDS[45] = "63201.3"
_FIELDS[46] = "4.8"
_FIELDS[47] = "1853.50"
_FIELDS[48] = "1516.50"
_FIELDS[49] = "1.5"
_FIELDS[52] = "24.0"
VALID = 'v_sh600519="' + "~".join(_FIELDS) + '";'


def test_tencent_quote_parses_basic():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _mock_resp(VALID)
        out = tencent_quote(["600519"])
    assert "600519" in out
    s = out["600519"]
    assert s["name"] == "贵州茅台"
    assert s["price"] == 1685.0
    assert s["pe_ttm"] == 22.5
    assert s["mcap_yi"] == 65432.1
    assert s["limit_up"] == 1853.5
    assert s["limit_down"] == 1516.5
    assert s["turnover_pct"] == 3.2


def test_tencent_quote_retries_on_failure():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [
            TimeoutError("first"),
            TimeoutError("second"),
            _mock_resp(VALID),
        ]
        with patch("time.sleep"):
            out = tencent_quote(["600519"])
    assert "600519" in out


def test_tencent_quote_handles_empty():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _mock_resp("")
        out = tencent_quote(["600519"])
    assert out == {}