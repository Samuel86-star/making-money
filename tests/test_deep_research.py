"""deep_research 单元测试. T_ 前缀测试数据, 不碰真实持仓.
重点测 thesis_breakers (论点破坏者, P0 新增) + catalysts 重定向."""
from a_stock.deep_research import (
    DeepResearch, thesis_breakers, dd_checklist, catalysts_list,
)


def _mk(**kw):
    """造测试 DeepResearch, 默认合理值."""
    base = dict(code="T_001", name="TEST", price=10.0, eps=0.5, pe_ttm=20,
                net_profit_yoy=15, roe=12, score=65, veto=False,
                veto_reason="", momentum_60d=5)
    base.update(kw)
    return DeepResearch(**base)


# === thesis_breakers ===

def test_thesis_breakers_normal_returns_list():
    """正常标的: 返回 list (可能含趋势/估值类触发条件)."""
    r = _mk()
    tb = thesis_breakers(r)
    assert isinstance(tb, list)


def test_thesis_breakers_growth_negative_triggers():
    """净利同比转负 → 成长论点失效触发."""
    r = _mk(net_profit_yoy=-25)
    tb = thesis_breakers(r)
    assert any("净利" in t or "成长" in t for t in tb), f"应有成长失效触发, got {tb}"


def test_thesis_breakers_deep_momentum_triggers():
    """60日动量<-15% 持续 → 趋势论点失效触发."""
    r = _mk(momentum_60d=-22)
    tb = thesis_breakers(r)
    assert any("动量" in t or "趋势" in t for t in tb), f"应有趋势失效触发, got {tb}"


def test_thesis_breakers_high_pe_triggers():
    """PE>80 → 估值论点失效触发."""
    r = _mk(pe_ttm=95)
    tb = thesis_breakers(r)
    assert any("PE" in t or "估值" in t for t in tb), f"应有估值失效触发, got {tb}"


def test_thesis_breakers_low_roe_triggers():
    """ROE 0<ROE<5 → 盈利能力弱触发."""
    r = _mk(roe=3)
    tb = thesis_breakers(r)
    assert any("ROE" in t or "盈利" in t for t in tb), f"应有盈利弱触发, got {tb}"


def test_thesis_breakers_strong_stock_few_triggers():
    """强标的 (高ROE/正增长/正常PE/正动量): 触发条目少 (<=2)."""
    r = _mk(roe=18, net_profit_yoy=25, pe_ttm=20, momentum_60d=10)
    tb = thesis_breakers(r)
    assert len(tb) <= 2, f"强标的触发应少, got {len(tb)}: {tb}"


def test_thesis_breakers_each_item_actionable():
    """每条触发应含可操作的退出条件 (带'退出'或'重评估'或具体阈值)."""
    r = _mk(net_profit_yoy=-25, momentum_60d=-22, pe_ttm=95, roe=3)
    tb = thesis_breakers(r)
    for t in tb:
        assert any(k in t for k in ["退出", "重评估", "止损", "<", ">", "%"]), \
            f"触发条目应可操作: {t}"


# === dd_checklist (回归, 确保不破) ===

def test_dd_checklist_no_flags_returns_ok():
    r = _mk()
    flags = dd_checklist(r)
    assert "✅ DD无明显红旗" in flags


def test_dd_checklist_low_roe_flag():
    r = _mk(roe=3)
    assert "ROE<5% 盈利能力弱" in dd_checklist(r)


# === catalysts_list ===

def test_catalysts_list_returns_list():
    """catalysts_list 不崩, 返回 list (可能空, 因 macro_calendar 无数据)."""
    cs = catalysts_list("T_001")
    assert isinstance(cs, list)


# === research 集成 (轻量, 不拉网络) ===

def test_research_includes_thesis_breakers_field(monkeypatch):
    """research() 输出 dict 含 thesis_breakers 字段."""
    from a_stock import deep_research as dr

    # mock 网络/parquet 依赖
    monkeypatch.setattr(dr, "_live_quote_safe", lambda code: {"price": 10.0})
    monkeypatch.setattr(dr, "_fetch_fundamentals", lambda code: (0.5, 20, 15, 12))
    monkeypatch.setattr(dr, "_momentum_from_parquet", lambda code: 5.0)
    monkeypatch.setattr(dr, "_score_safe", lambda code, name: (65, False, ""))
    monkeypatch.setattr(dr, "catalysts_list", lambda code: ["2026-07-15 财报季"])

    r = dr.research("T_001", "TEST", price=10.0)
    assert "thesis_breakers" in r, "research 输出应含 thesis_breakers"
    assert isinstance(r["thesis_breakers"], list)
