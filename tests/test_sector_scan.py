from unittest.mock import patch, MagicMock
from py.a_screen.sector_scan import scan_sectors


def test_scan_sectors_combines_sources():
    with patch("py.a_screen.sector_scan.industry_comparison") as m1, \
         patch("py.a_screen.sector_scan.ths_hot_reason") as m2, \
         patch("py.a_screen.sector_scan.daily_dragon_tiger") as m3:
        m1.return_value = {"top": [{"name": "白酒", "change_pct": 1.0}], "bottom": [], "total": 0}
        m2.return_value = [{"code": "600519", "name": "贵州茅台", "reason": "白酒提价"}]
        m3.return_value = {"data": [{"code": "000858", "name": "五粮液", "net_buy": 1e8}]}

        result = scan_sectors("2026-06-26")

    assert "industry" in result
    assert "hot" in result
    assert "dragon_tiger" in result
    assert result["industry"][0]["name"] == "白酒"