"""行业资金流工具测试 (07-01上午实战新增).

验证:
- sectors.industry_fund_flow(): dedupe + 净流单位正确(元→亿)
- close_scan 将 industry_flow 写入 result
"""


def test_industry_fund_flow_dedup_and_unit(monkeypatch):
    import a_stock.a_stock_data.sectors as sectors

    # 模拟 industry_comparison(top_n=100) 返回 top/bottom重复行, net_flow当前为 f62*10000(元)
    # net_flow 当前口径 = f62 元; net_flow_yi = net_flow/1e8
    row_in = {"code": "BK1", "name": "非银金融", "change_pct": 4.5,
              "net_flow": 6983000000, "leader": "600909"}  # 69.83亿
    row_out = {"code": "BK2", "name": "电子", "change_pct": 0.5,
               "net_flow": -21401000000, "leader": "002273"}  # -214.01亿
    monkeypatch.setattr(sectors, "industry_comparison", lambda top_n=100: {
        "top": [row_in, row_out], "bottom": [row_in, row_out], "total": 2
    })

    r = sectors.industry_fund_flow(top_n=1)
    assert r["total"] == 2
    assert len(r["inflow_top"]) == 1
    assert len(r["outflow_top"]) == 1
    assert r["inflow_top"][0]["name"] == "非银金融"
    assert abs(r["inflow_top"][0]["net_flow_yi"] - 69.83) < 0.01
    assert r["outflow_top"][0]["name"] == "电子"
    assert abs(r["outflow_top"][0]["net_flow_yi"] + 214.01) < 0.01


def test_close_scan_includes_industry_flow(monkeypatch):
    import a_stock.close_scan as cs

    monkeypatch.setattr(cs, "_init_db", lambda: None)
    monkeypatch.setattr("a_stock.sector_rotation.snapshot_today", lambda: None, raising=False)
    monkeypatch.setattr("a_stock.sector_rotation.analyze", lambda: None, raising=False)
    monkeypatch.setattr("a_stock.sentiment.compute_temp", lambda: {"temp": 30.0, "mood": "谨慎"}, raising=False)
    monkeypatch.setattr("a_stock.market_regime.regime", lambda code: {"level": "NORMAL", "dist_count": 0, "ftd": None}, raising=False)
    monkeypatch.setattr("a_stock.anomaly_holdings_loader.load_targets", lambda: [], raising=False)
    monkeypatch.setattr("a_stock.a_stock_data.sectors.industry_fund_flow", lambda top_n=10: {
        "inflow_top": [{"name": "非银金融", "change_pct": 4.5, "net_flow_yi": 68.83}],
        "outflow_top": [{"name": "电子", "change_pct": 0.5, "net_flow_yi": -212.46}],
        "total": 2,
    }, raising=False)

    r = cs.run(dry_run=True)
    assert "industry_flow" in r
    assert r["industry_flow"]["inflow_top"][0]["name"] == "非银金融"
    assert r["industry_flow"]["outflow_top"][0]["name"] == "电子"
