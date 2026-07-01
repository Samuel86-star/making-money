"""morning_scan confluence 接入测试.
验证 _confluence_enrich: 2信号+10/3+-5/0-1不变. signal_fns可注入(mock)."""
from a_stock.morning_scan import _confluence_enrich


def _scored(code, total=60):
    return {"code": code, "name": code, "total": total, "level": "观望偏多",
            "net_flow_yi": 0.5, "factors": {}}


def _patch_ohlcv(monkeypatch, code_to_fires):
    """patch ohlcv.load_ohlcv: 返回长度足够的假df. 真实信号判定靠注入signal_fns.
    code_to_fires: {code: [signal_indices that fire]}."""
    import pandas as pd
    import a_stock.ohlcv as ohlcv

    def fake_load(code):
        # 造100行 df (够所有detector的最小长度)
        return pd.DataFrame({"close": [10.0]*100, "volume": [1000]*100})
    monkeypatch.setattr(ohlcv, "load_ohlcv", fake_load)


def test_confluence_2_signals_boosts_10(monkeypatch):
    """2信号叠加 → total +10, 标 confluence 字段."""
    _patch_ohlcv(monkeypatch, None)
    scored = [_scored("T_C2", 60)]
    fns = [lambda c, v: True, lambda c, v: True,   # 2 fire
           lambda c, v: False, lambda c, v: False, lambda c, v: False]
    names = ["VCP", "Wyckoff吸筹", "Wyckoff派发", "Turtle sys1", "Turtle sys2"]
    _confluence_enrich(scored, signal_fns=fns, signal_names=names)
    assert scored[0]["total"] == 70
    assert len(scored[0]["confluence"]) == 2
    assert "confluence_warn" not in scored[0]


def test_confluence_3plus_penalty_5(monkeypatch):
    """3+信号 → total -5, 标 confluence_warn 过热."""
    _patch_ohlcv(monkeypatch, None)
    scored = [_scored("T_C3", 60)]
    fns = [lambda c, v: True]*3 + [lambda c, v: False]*2  # 3 fire
    names = ["VCP", "Wyckoff吸筹", "Wyckoff派发", "Turtle sys1", "Turtle sys2"]
    _confluence_enrich(scored, signal_fns=fns, signal_names=names)
    assert scored[0]["total"] == 55
    assert scored[0]["confluence_warn"] == "3+信号过热"


def test_confluence_1_signal_no_boost(monkeypatch):
    """单信号 (edge≈base) → total 不变, 无confluence字段."""
    _patch_ohlcv(monkeypatch, None)
    scored = [_scored("T_C1", 60)]
    fns = [lambda c, v: True] + [lambda c, v: False]*4
    names = ["VCP", "Wyckoff吸筹", "Wyckoff派发", "Turtle sys1", "Turtle sys2"]
    _confluence_enrich(scored, signal_fns=fns, signal_names=names)
    assert scored[0]["total"] == 60
    assert "confluence" not in scored[0]


def test_confluence_0_signals_no_boost(monkeypatch):
    """无信号 → total 不变."""
    _patch_ohlcv(monkeypatch, None)
    scored = [_scored("T_C0", 60)]
    fns = [lambda c, v: False]*5
    names = ["VCP"]*5
    _confluence_enrich(scored, signal_fns=fns, signal_names=names)
    assert scored[0]["total"] == 60
    assert "confluence" not in scored[0]


def test_confluence_no_ohlcv_skips(monkeypatch):
    """parquet缺失 → 跳过, 不崩, total不变."""
    import a_stock.ohlcv as ohlcv
    monkeypatch.setattr(ohlcv, "load_ohlcv", lambda c: (_ for _ in ()).throw(FileNotFoundError()))
    scored = [_scored("T_NODATA", 60)]
    _confluence_enrich(scored)  # 用默认真实signal_fns
    assert scored[0]["total"] == 60


def test_confluence_short_history_skips(monkeypatch):
    """数据<60日 → 跳过 (detectors不够)."""
    import pandas as pd
    import a_stock.ohlcv as ohlcv
    monkeypatch.setattr(ohlcv, "load_ohlcv",
                        lambda c: pd.DataFrame({"close": [10.0]*30, "volume": [1000]*30}))
    scored = [_scored("T_SHORT", 60)]
    _confluence_enrich(scored)
    assert scored[0]["total"] == 60


def test_confluence_signal_exception_counted_as_not_fired(monkeypatch):
    """某signal_fn抛异常 → 当未fire, 不崩, 其他正常."""
    _patch_ohlcv(monkeypatch, None)
    scored = [_scored("T_ERR", 60)]
    fns = [lambda c, v: True, lambda c, v: 1/0, lambda c, v: True] + [lambda c, v: False]*2
    names = ["VCP", "Wyckoff吸筹", "Wyckoff派发", "Turtle sys1", "Turtle sys2"]
    _confluence_enrich(scored, signal_fns=fns, signal_names=names)
    # 2个有效fire (1抛异常当未fire) → +10
    assert scored[0]["total"] == 70
