"""edge_scanner 单元测试.
扫全市场找当前命中验证setup的股 → actionable sized建议.
mock SETUP_FNS + parquet, 不依赖真实数据."""
import pandas as pd
from unittest.mock import patch


def _make_parquet(code, close=10.0, n=100, tmp_path=None):
    """造 parquet 文件 (真)."""
    import a_stock.config as cfg
    d = tmp_path or cfg.OHLCV_DIR
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": [close]*n, "volume": [1000]*n,
                  "high": [close]*n, "low": [close]*n}).to_parquet(d / f"{code}.parquet")


def _registry():
    return {
        "强setup": {"win_rate": 0.5, "payoff": 2.0, "expectancy": 0.02, "kelly_frac": 0.1, "n": 100},
        "弱setup": {"win_rate": 0.4, "payoff": 1.5, "expectancy": 0.005, "kelly_frac": 0.03, "n": 50},
    }


def test_scan_finds_setup_hits(tmp_path, monkeypatch):
    """命中setup的股被收集."""
    import a_stock.config as cfg
    monkeypatch.setattr(cfg, "OHLCV_DIR", tmp_path)
    _make_parquet("T_HIT1", 10.0, 100, tmp_path)
    _make_parquet("T_HIT2", 20.0, 100, tmp_path)
    _make_parquet("T_MISS", 10.0, 100, tmp_path)
    import a_stock.edge_scanner as es
    import a_stock.setup_registry as sr
    # mock detect_setup: T_HIT1/T_HIT2命中, T_MISS不中
    monkeypatch.setattr(es, "detect_setup",
                        lambda c, registry=None: "强setup" if c.startswith("T_HIT") else None)
    monkeypatch.setattr(es, "load_registry", lambda: _registry())
    monkeypatch.setattr(es, "_stock_name", lambda c: c)
    recs = es.scan_for_setups(capital=80000, stop_pct=0.05)
    codes = [r["code"] for r in recs]
    assert "T_HIT1" in codes and "T_HIT2" in codes
    assert "T_MISS" not in codes


def test_scan_ranks_by_setup_expectancy(tmp_path, monkeypatch):
    """高期望setup的股排前."""
    import a_stock.config as cfg
    monkeypatch.setattr(cfg, "OHLCV_DIR", tmp_path)
    _make_parquet("T_STRONG", 10.0, 100, tmp_path)
    _make_parquet("T_WEAK", 10.0, 100, tmp_path)
    import a_stock.edge_scanner as es
    import a_stock.setup_registry as sr
    monkeypatch.setattr(es, "detect_setup",
                        lambda c, registry=None: "强setup" if "STRONG" in c else "弱setup")
    monkeypatch.setattr(es, "load_registry", lambda: _registry())
    monkeypatch.setattr(es, "_stock_name", lambda c: c)
    recs = es.scan_for_setups(capital=80000, stop_pct=0.05)
    assert recs[0]["code"] == "T_STRONG"  # 强setup期望高排前


def test_scan_target_from_payoff(tmp_path, monkeypatch):
    """目标价 = price × (1 + payoff × stop_pct). 强setup payoff2, stop5% → +10%."""
    import a_stock.config as cfg
    monkeypatch.setattr(cfg, "OHLCV_DIR", tmp_path)
    _make_parquet("T_X", 10.0, 100, tmp_path)
    import a_stock.edge_scanner as es
    import a_stock.setup_registry as sr
    monkeypatch.setattr(es, "detect_setup", lambda c, registry=None: "强setup")
    monkeypatch.setattr(es, "load_registry", lambda: _registry())
    monkeypatch.setattr(es, "_stock_name", lambda c: c)
    recs = es.scan_for_setups(capital=80000, stop_pct=0.05)
    r = recs[0]
    assert abs(r["entry"] - 10.0) < 1e-9
    assert abs(r["stop"] - 9.5) < 1e-9          # 10 × 0.95
    assert abs(r["target"] - 11.0) < 1e-9        # 10 × (1 + 2.0×0.05)


def test_scan_output_has_sizing(tmp_path, monkeypatch):
    """每条建议含 shares/kelly_frac/setup."""
    import a_stock.config as cfg
    monkeypatch.setattr(cfg, "OHLCV_DIR", tmp_path)
    _make_parquet("T_X", 10.0, 100, tmp_path)
    import a_stock.edge_scanner as es
    import a_stock.setup_registry as sr
    monkeypatch.setattr(es, "detect_setup", lambda c, registry=None: "强setup")
    monkeypatch.setattr(es, "load_registry", lambda: _registry())
    monkeypatch.setattr(es, "_stock_name", lambda c: c)
    recs = es.scan_for_setups(capital=80000, stop_pct=0.05)
    r = recs[0]
    assert r["shares"] % 100 == 0      # A股100整手
    assert r["setup"] == "强setup"
    assert r["kelly_frac"] > 0


def test_scan_filters_sub_cost_edge(tmp_path, monkeypatch):
    """net expectancy (扣成本) ≤ 0 的setup被滤 (不值得交易)."""
    import a_stock.config as cfg
    monkeypatch.setattr(cfg, "OHLCV_DIR", tmp_path)
    _make_parquet("T_LOW", 10.0, 100, tmp_path)
    import a_stock.edge_scanner as es
    import a_stock.setup_registry as sr
    # 弱setup期望0.5%, 成本0.3% → 净0.2% (仍正, 保留) vs 若期望0.2%净-0.1滤除
    monkeypatch.setattr(es, "detect_setup", lambda c, registry=None: "弱setup")
    low_reg = {"弱setup": {"win_rate": 0.4, "payoff": 1.5, "expectancy": 0.002,
                           "kelly_frac": 0.02, "n": 50}}  # 0.2% < 0.3%成本
    monkeypatch.setattr(es, "load_registry", lambda: low_reg)
    monkeypatch.setattr(es, "_stock_name", lambda c: c)
    recs = es.scan_for_setups(capital=80000, stop_pct=0.05, cost_pct=0.003)
    assert recs == []  # 净期望≤0, 滤除


def test_scan_no_parquet_skips(tmp_path, monkeypatch):
    """无parquet不崩, 返回空."""
    import a_stock.config as cfg
    monkeypatch.setattr(cfg, "OHLCV_DIR", tmp_path)
    import a_stock.edge_scanner as es
    recs = es.scan_for_setups(capital=80000)
    assert recs == []
