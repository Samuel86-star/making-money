"""行业资金流工具测试 (07-01上午实战新增).

验证:
- sectors.industry_fund_flow(): dedupe + 净流单位正确(元→亿)
- close_scan 将 industry_flow 写入 result
"""


def test_industry_fund_flow_dedup_and_unit(monkeypatch):
    import a_stock.a_stock_data.sectors as sectors

    # 模拟 industry_comparison(top_n=100) 返回 top/bottom重复行; net_flow 当前口径 = f62 元
    # net_flow_yi = net_flow/1e8
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


def test_close_scan_persists_industry_flow(monkeypatch, tmp_path):
    """非dry_run时 daily_close 持久化 industry_flow JSON, 供历史复盘查询."""
    import json
    import sqlite3
    import a_stock.close_scan as cs
    import a_stock.config as cfg

    db_path = tmp_path / "screener.sqlite"
    monkeypatch.setattr(cfg, "SCREENER_DB", db_path)
    monkeypatch.setattr("a_stock.sector_rotation.snapshot_today", lambda: None, raising=False)
    monkeypatch.setattr("a_stock.sector_rotation.analyze", lambda: None, raising=False)
    monkeypatch.setattr("a_stock.sentiment.compute_temp", lambda: {"temp": 30.0, "mood": "谨慎"}, raising=False)
    monkeypatch.setattr("a_stock.market_regime.regime", lambda code: {"level": "NORMAL", "dist_count": 0, "ftd": None}, raising=False)
    monkeypatch.setattr("a_stock.anomaly_holdings_loader.load_targets", lambda: [], raising=False)
    payload = {
        "inflow_top": [{"name": "非银金融", "change_pct": 4.5, "net_flow_yi": 68.83}],
        "outflow_top": [{"name": "电子", "change_pct": 0.5, "net_flow_yi": -212.46}],
        "total": 2,
    }
    monkeypatch.setattr("a_stock.a_stock_data.sectors.industry_fund_flow", lambda top_n=10: payload, raising=False)
    monkeypatch.setattr("a_stock.close_scan.push", lambda *args, **kwargs: None)

    r = cs.run(dry_run=False)
    assert r["industry_flow"] == payload
    con = sqlite3.connect(db_path)
    cols = [row[1] for row in con.execute("PRAGMA table_info(daily_close)")]
    assert "industry_flow" in cols
    row = con.execute("SELECT industry_flow FROM daily_close WHERE date=?", (r["date"],)).fetchone()
    saved = json.loads(row[0])
    assert saved["inflow_top"][0]["name"] == "非银金融"


def test_close_scan_retries_industry_flow(monkeypatch):
    """Issue3: 拉取第一次失败第二次成功 → 重试生效, industry_flow 正常写入."""
    import a_stock.close_scan as cs
    calls = []

    def flaky(top_n=10):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("network")
        return {"inflow_top": [{"name": "非银", "change_pct": 4.5, "net_flow_yi": 68.0}],
                "outflow_top": [{"name": "电子", "change_pct": 0.5, "net_flow_yi": -212.0}],
                "total": 2}

    monkeypatch.setattr(cs, "_init_db", lambda: None)
    monkeypatch.setattr("a_stock.sector_rotation.snapshot_today", lambda: None, raising=False)
    monkeypatch.setattr("a_stock.sector_rotation.analyze", lambda: None, raising=False)
    monkeypatch.setattr("a_stock.sentiment.compute_temp", lambda: {"temp": 30.0, "mood": "谨慎"}, raising=False)
    monkeypatch.setattr("a_stock.market_regime.regime", lambda code: {"level": "NORMAL", "dist_count": 0, "ftd": None}, raising=False)
    monkeypatch.setattr("a_stock.anomaly_holdings_loader.load_targets", lambda: [], raising=False)
    monkeypatch.setattr("a_stock.a_stock_data.sectors.industry_fund_flow", flaky, raising=False)
    monkeypatch.setattr(cs, "push", lambda *a, **k: None)

    r = cs.run(dry_run=True)
    assert len(calls) == 2  # 重试1次后成功
    assert r["industry_flow"]["total"] == 2


def test_close_scan_industry_flow_failure_warns(monkeypatch):
    """Issue3: 全失败 → result记 error + 推送 warning (不再静默NULL)."""
    import a_stock.close_scan as cs
    pushes = []

    def fake_push(title, body, subtitle=None, **k):
        pushes.append((title, body))

    def always_fail(top_n=10):
        raise TimeoutError("timeout")

    monkeypatch.setattr(cs, "_init_db", lambda: None)
    monkeypatch.setattr("a_stock.sector_rotation.snapshot_today", lambda: None, raising=False)
    monkeypatch.setattr("a_stock.sector_rotation.analyze", lambda: None, raising=False)
    monkeypatch.setattr("a_stock.sentiment.compute_temp", lambda: {"temp": 30.0, "mood": "谨慎"}, raising=False)
    monkeypatch.setattr("a_stock.market_regime.regime", lambda code: {"level": "NORMAL", "dist_count": 0, "ftd": None}, raising=False)
    monkeypatch.setattr("a_stock.anomaly_holdings_loader.load_targets", lambda: [], raising=False)
    monkeypatch.setattr("a_stock.a_stock_data.sectors.industry_fund_flow", always_fail, raising=False)
    monkeypatch.setattr(cs, "push", fake_push)

    r = cs.run(dry_run=True)
    assert r.get("industry_flow") is None
    assert "industry_flow_error" in r
    assert "timeout" in r["industry_flow_error"]
    warned = any("资金流" in t for t, _ in pushes)
    assert warned, f"应推送资金流缺失warning, pushes={pushes}"


def test_close_scan_industry_flow_empty_result_warns(monkeypatch):
    """Issue3 防御: fetch 返回 None (非异常) 也视为失败 → 重试 + 告警, 不静默."""
    import a_stock.close_scan as cs
    pushes = []

    def fake_push(title, body, subtitle=None, **k):
        pushes.append((title, body))

    def empty(top_n=10):
        return None  # 非异常, 但空

    monkeypatch.setattr(cs, "_init_db", lambda: None)
    monkeypatch.setattr("a_stock.sector_rotation.snapshot_today", lambda: None, raising=False)
    monkeypatch.setattr("a_stock.sector_rotation.analyze", lambda: None, raising=False)
    monkeypatch.setattr("a_stock.sentiment.compute_temp", lambda: {"temp": 30.0, "mood": "谨慎"}, raising=False)
    monkeypatch.setattr("a_stock.market_regime.regime", lambda code: {"level": "NORMAL", "dist_count": 0, "ftd": None}, raising=False)
    monkeypatch.setattr("a_stock.anomaly_holdings_loader.load_targets", lambda: [], raising=False)
    monkeypatch.setattr("a_stock.a_stock_data.sectors.industry_fund_flow", empty, raising=False)
    monkeypatch.setattr(cs, "push", fake_push)

    r = cs.run(dry_run=True)
    assert r.get("industry_flow") is None
    assert "industry_flow_error" in r
    assert r["industry_flow_error"] == "返回空结果"
    warned = any("资金流" in t for t, _ in pushes)
    assert warned, f"空返回应推送warning, pushes={pushes}"
