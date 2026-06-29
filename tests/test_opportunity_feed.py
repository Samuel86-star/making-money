"""opportunity_feed 单元测试. mock 各数据源, 验证4类机会聚合+排序."""
from a_stock.web.opportunity_feed import collect_opportunities


def test_collect_aggregates_four_types(monkeypatch):
    """4类机会都被收集."""
    monkeypatch.setattr("a_stock.web.opportunity_feed._pullback_signals",
                        lambda: [{"code": "159801", "name": "芯片ETF", "ma": "MA5",
                                  "price": 1.545, "cost": 1.541}])
    monkeypatch.setattr("a_stock.web.opportunity_feed._anomaly_signals",
                        lambda: [{"code": "002409", "name": "雅克科技",
                                  "desc": "资金流#7 收涨+4.6%", "change": 4.6}])
    monkeypatch.setattr("a_stock.web.opportunity_feed._candidate_signals",
                        lambda: [{"code": "000988", "name": "华工科技",
                                  "score": 63.0, "desc": "观望偏多"}])
    monkeypatch.setattr("a_stock.web.opportunity_feed._rule_signals",
                        lambda: [{"code": "159516", "name": "半导体材料设备ETF",
                                  "desc": "回踩<=1.85试仓", "trigger_price": 1.85,
                                  "current": 1.921, "fired": False}])
    opps = collect_opportunities()
    types = {o["type"] for o in opps}
    assert types == {"pullback", "anomaly", "candidate", "rule"}
    for o in opps:
        assert {"type", "time", "code", "name", "desc", "meta", "tag", "action_label"} <= o.keys()


def test_rule_unfired_marked_pending(monkeypatch):
    """未触发规则标"待触"时间."""
    monkeypatch.setattr("a_stock.web.opportunity_feed._pullback_signals", lambda: [])
    monkeypatch.setattr("a_stock.web.opportunity_feed._anomaly_signals", lambda: [])
    monkeypatch.setattr("a_stock.web.opportunity_feed._candidate_signals", lambda: [])
    monkeypatch.setattr("a_stock.web.opportunity_feed._rule_signals",
                        lambda: [{"code": "159516", "name": "半导体材料设备ETF",
                                  "desc": "回踩<=1.85试仓", "trigger_price": 1.85,
                                  "current": 1.921, "fired": False}])
    opps = collect_opportunities()
    assert len(opps) == 1
    assert opps[0]["time"] == "待触"
    assert opps[0]["action_label"] is None


def test_empty_when_all_sources_empty(monkeypatch):
    """全部数据源空 → 空列表, 不崩."""
    for src in ["_pullback_signals", "_anomaly_signals", "_candidate_signals", "_rule_signals"]:
        monkeypatch.setattr(f"a_stock.web.opportunity_feed.{src}", lambda: [])
    assert collect_opportunities() == []


def test_pullback_uses_real_scorer(tmp_path, monkeypatch):
    """_pullback_signals 真实调用: 对持仓+watchlist跑scorer, 识别回踩."""
    from a_stock.scorers import technical_scorer
    closes = [10.0 + i * 0.1 for i in range(65)]
    closes[-1] = closes[-2] * 0.995
    rows = [{"date": f"2026-01-{i+1:02d}", "open": c, "high": c, "low": c,
             "close": c, "volume": 1000} for i, c in enumerate(closes)]
    monkeypatch.setattr(technical_scorer, "_load_ohlcv", lambda code, days=120: rows)
    monkeypatch.setattr("a_stock.web.opportunity_feed._watched_codes",
                        lambda: ["T_REAL1"])
    monkeypatch.setattr("a_stock.web.opportunity_feed._holding_cost",
                        lambda code: 10.0)
    from a_stock.web.opportunity_feed import _pullback_signals
    sigs = _pullback_signals()
    assert len(sigs) == 1
    assert sigs[0]["code"] == "T_REAL1"
    assert "MA5" in sigs[0]["ma"]


def test_positions_with_cost_and_stop_loss(monkeypatch):
    """持仓数据含 cost, stop_loss (ATR), pnl."""
    from a_stock.web import positions_panel
    monkeypatch.setattr("a_stock.web.positions_panel._load_positions",
                        lambda: [{"code": "T_POS1", "name": "T持仓", "qty": 100,
                                  "cost": 10.0, "price": 11.0,
                                  "unrealized_pnl": 100.0, "mv": 1100.0}])
    monkeypatch.setattr("a_stock.web.positions_panel._atr_stop",
                        lambda code, cost: 9.5)
    rows = positions_panel.collect_positions()
    assert len(rows) == 1
    r = rows[0]
    assert r["code"] == "T_POS1"
    assert r["cost"] == 10.0
    assert r["price"] == 11.0
    assert r["stop_loss"] == 9.5
    assert r["pnl_pct"] == 10.0  # (11-10)/10*100


def test_positions_empty_when_no_holdings(monkeypatch):
    """无持仓 → 空列表."""
    from a_stock.web import positions_panel
    monkeypatch.setattr("a_stock.web.positions_panel._load_positions", lambda: [])
    assert positions_panel.collect_positions() == []