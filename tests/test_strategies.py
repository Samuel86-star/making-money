"""strategies/ 单元测试. T_ 前缀测试数据, 不碰真实持仓."""
from a_stock.strategies.signals import Signal, SignalVote, aggregate


def test_signal_fields():
    s = Signal(code="T_001", name="TEST", action="buy", confidence=0.7,
               strategy="trend_breakout", reason="突破")
    assert s.code == "T_001"
    assert s.action == "buy"
    assert s.confidence == 0.7
    assert s.meta is None


def test_aggregate_multi_strategy_same_code():
    """同 code 被 2 策略命中 → total_confidence = 0.7+0.6."""
    sigs = [
        Signal("T_001", "A", "buy", 0.7, "trend_breakout", "突破"),
        Signal("T_001", "A", "buy", 0.6, "moneyflow_surge", "资金"),
    ]
    votes = aggregate(sigs)
    assert len(votes) == 1
    assert votes[0].code == "T_001"
    assert abs(votes[0].total_confidence - 1.3) < 1e-9
    assert set(votes[0].strategies) == {"trend_breakout", "moneyflow_surge"}


def test_aggregate_sorted_by_confidence_desc():
    sigs = [
        Signal("T_002", "B", "buy", 0.5, "oversold_bounce", "超跌"),
        Signal("T_001", "A", "buy", 0.7, "trend_breakout", "突破"),
    ]
    votes = aggregate(sigs)
    assert votes[0].code == "T_001"  # 0.7 > 0.5
    assert votes[1].code == "T_002"


def test_aggregate_ignores_non_buy():
    sigs = [
        Signal("T_001", "A", "hold", 0.9, "x", "观望"),
        Signal("T_001", "A", "buy", 0.7, "y", "买"),
    ]
    votes = aggregate(sigs)
    assert len(votes) == 1
    assert abs(votes[0].total_confidence - 0.7) < 1e-9


def test_aggregate_top_reason_is_highest_confidence():
    sigs = [
        Signal("T_001", "A", "buy", 0.5, "low", "弱理由"),
        Signal("T_001", "A", "buy", 0.7, "high", "强理由"),
    ]
    votes = aggregate(sigs)
    assert votes[0].top_reason == "强理由"


def test_aggregate_top_reason_tie_keeps_first():
    """#7: 两信号同 confidence → top_reason 是先 append 的那条 (平局保留先到, 跨次稳定).

    旧代码 `>=` 让后迭代信号覆盖; 新代码 `>` + `signals[:-1]` 平局不覆盖.
    """
    sigs = [
        Signal("T_001", "A", "buy", 0.6, "moneyflow_surge", "先到理由"),
        Signal("T_001", "A", "buy", 0.6, "near_limit_up", "后到理由"),
    ]
    votes = aggregate(sigs)
    assert len(votes) == 1
    assert votes[0].top_reason == "先到理由", "平局应保留先 append 的信号 reason"


def test_aggregate_top_reason_first_signal_always_set():
    """#7 边界: 首条信号 (空 signals[:-1], default=-1) → top_reason 必设为首条 reason."""
    sigs = [
        Signal("T_002", "B", "buy", 0.0, "x", "首条理由"),
    ]
    votes = aggregate(sigs)
    assert votes[0].top_reason == "首条理由"


def test_aggregate_top_reason_higher_overrides_after_tie():
    """#7: 平局保留先到, 但更高 confidence 仍覆盖 (验证 > 不破坏正常更新)."""
    sigs = [
        Signal("T_001", "A", "buy", 0.6, "a", "先到0.6"),
        Signal("T_001", "A", "buy", 0.6, "b", "平局0.6"),
        Signal("T_001", "A", "buy", 0.8, "c", "更高0.8"),
    ]
    votes = aggregate(sigs)
    assert votes[0].top_reason == "更高0.8"


def test_aggregate_empty():
    assert aggregate([]) == []


from a_stock.strategies.base import StrategyMeta, BaseStrategy, limit_pct


def test_limit_pct_main_board():
    assert limit_pct("600276") == 10.0
    assert limit_pct("000001") == 10.0


def test_limit_pct_gem_star():
    assert limit_pct("300059") == 20.0  # 创业板
    assert limit_pct("688981") == 20.0  # 科创板


def test_limit_pct_etf():
    # 60/68 开头按 20%, ETF 5/1 开头主板 10%
    assert limit_pct("515650") == 10.0


def test_base_evaluate_swallows_exception():
    """signals 抛错 → evaluate 返回 [], 不传播."""
    class BoomStrategy(BaseStrategy):
        META = StrategyMeta("boom", 0.5, "炸")
        def filter(self, code, name):
            return True
        def signals(self, code, name):
            raise RuntimeError("炸了")

    sigs = BoomStrategy().evaluate("T_001", "X")
    assert sigs == []


def test_base_evaluate_filter_blocks_signals():
    """filter False → 不跑 signals."""
    class FilterStrategy(BaseStrategy):
        META = StrategyMeta("filt", 0.5, "筛")
        called = False
        def filter(self, code, name):
            return False
        def signals(self, code, name):
            FilterStrategy.called = True
            return []

    FilterStrategy().evaluate("T_001", "X")
    assert FilterStrategy.called is False


def test_registry_get_all_returns_strategies():
    """registry 扫描目录后, 至少能 import 不报错 (策略文件此时还没建, 只验扫描不炸)."""
    from a_stock.strategies import registry
    registry._scan()  # 此时策略文件未建, 应返回空不报错
    assert isinstance(registry.get_all(), list)


def test_registry_get_unknown_returns_none():
    from a_stock.strategies import registry
    registry._scan()
    assert registry.get("nonexistent_strategy") is None


# ===== Batch B: strategy implementations (Task 7-11) =====

def test_trend_breakout_hit(monkeypatch):
    """末根创60日新高 + 站上ma60 + 量比≥2 → 1信号 0.7."""
    from a_stock.strategies import runner
    from a_stock.strategies.trend_breakout import TrendBreakout
    runner.clear_cache()
    # 60根递增, 末根创新高, 末根量 30000 (5日均 10000 → 量比3)
    monkeypatch.setattr(runner, "_load_ohlcv",
                        lambda c: _make_breakout_ohlcv(hit=True))
    sigs = TrendBreakout().signals("T_001", "A")
    assert len(sigs) == 1
    assert sigs[0].confidence == 0.7
    assert sigs[0].strategy == "trend_breakout"


def test_trend_breakout_miss_no_new_high(monkeypatch):
    from a_stock.strategies import runner
    from a_stock.strategies.trend_breakout import TrendBreakout
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv",
                        lambda c: _make_breakout_ohlcv(hit=False))
    assert TrendBreakout().signals("T_001", "A") == []


def test_trend_breakout_filter_data_too_short(monkeypatch):
    from a_stock.strategies import runner
    from a_stock.strategies.trend_breakout import TrendBreakout
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_short_ohlcv())
    assert TrendBreakout().filter("T_001", "A") is False


def _make_breakout_ohlcv(hit: bool):
    """70根. hit=True: 末根创新高+量比大; hit=False: 末根不创新高."""
    import pandas as pd
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    closes = [10.0 + i * 0.01 for i in range(n - 1)]
    last_close = 11.0 if hit else 10.0  # hit 超过前面所有
    closes.append(last_close)
    highs = [c + 0.05 for c in closes[:-1]] + [last_close + 0.1]
    df = pd.DataFrame({"date": dates, "open": closes[:],
                       "high": highs, "low": [c - 0.05 for c in closes],
                       "close": closes, "volume": [10000] * (n - 1) + [30000]})
    return df


def _make_short_ohlcv():
    import pandas as pd
    n = 40
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    closes = [10.0] * n
    return pd.DataFrame({"date": dates, "open": closes, "high": closes,
                         "low": closes, "close": closes, "volume": [10000] * n})


def test_oversold_bounce_hit(monkeypatch):
    """RSI<30 + 收阳 + 量比≥1.2 → 1信号 0.5."""
    from a_stock.strategies import runner
    from a_stock.strategies.oversold_bounce import OversoldBounce
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_rsi_ohlcv(rsi_below_30=True))
    sigs = OversoldBounce().signals("T_001", "A")
    assert len(sigs) == 1
    assert sigs[0].confidence == 0.5


def test_oversold_bounce_miss_rsi_high(monkeypatch):
    from a_stock.strategies import runner
    from a_stock.strategies.oversold_bounce import OversoldBounce
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_rsi_ohlcv(rsi_below_30=False))
    assert OversoldBounce().signals("T_001", "A") == []


def _make_rsi_ohlcv(rsi_below_30: bool):
    """构造让 RSI<30 (连跌) 或 RSI 高 (连涨) 的序列. 末根收阳 + 量比大."""
    import pandas as pd
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    if rsi_below_30:
        # 前 69 根持续下跌, 末根反弹收阳
        closes = [20.0 - i * 0.2 for i in range(n - 1)] + [13.0]
        opens = closes[:]
        opens[-1] = 12.5  # 末根开低于收, 收阳
    else:
        closes = [10.0 + i * 0.1 for i in range(n - 1)] + [17.0]
        opens = closes[:]
        opens[-1] = 16.5
    highs = [max(o, c) + 0.05 for o, c in zip(opens, closes)]
    lows = [min(o, c) - 0.05 for o, c in zip(opens, closes)]
    vols = [10000] * (n - 1) + [15000]  # 量比 1.5
    return pd.DataFrame({"date": dates, "open": opens, "high": highs,
                         "low": lows, "close": closes, "volume": vols})


def test_near_limit_up_hit(monkeypatch):
    """涨8% (主板涨停10%) 距涨停2% → 触发 0.6."""
    from a_stock.strategies import runner
    from a_stock.strategies.near_limit_up import NearLimitUp
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_limit_ohlcv(change_pct=8.0))
    sigs = NearLimitUp().signals("T_600000", "A")  # 主板 10%
    assert len(sigs) == 1
    assert sigs[0].confidence == 0.6


def test_near_limit_up_miss_already_sealed(monkeypatch):
    """涨9.9% 且 high 触及涨停价(封板) → 不触发. 真实封板形态: high==round涨停价."""
    from a_stock.strategies import runner
    from a_stock.strategies.near_limit_up import NearLimitUp
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_sealed_ohlcv())
    assert NearLimitUp().signals("T_600000", "A") == []


def _make_sealed_ohlcv():
    """真实封板形态: prev_close=10.0, 涨停价=round(11.0,2)=11.0, high==11.0 触及=封板.
    change_pct=10.0 (实际封板), 但 high 触及涨停价 → 未封板检查拦截."""
    import pandas as pd
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    base = 10.0
    # 末根 close = 涨停价 11.0 (封板), open = prev_close, high = 11.0 (触及)
    closes = [base] * (n - 1) + [11.0]
    opens = closes[:]
    opens[-1] = base
    highs = [c + 0.05 for c in closes[:-1]] + [11.0]  # 末根 high = 涨停价 (触及=封板)
    lows = [c - 0.05 for c in closes[:-1]] + [base]
    return pd.DataFrame({"date": dates, "open": opens, "high": highs,
                         "low": lows, "close": closes, "volume": [10000] * n})


def test_near_limit_up_rounded_limit_price_blocks_seal(monkeypatch):
    """涨停价四舍五入到分: prev_close=10.03 → 涨停价 11.03 (非 11.033).
    high 触及 11.03=封板, 但 close=11.02 (涨9.87%, dist0.13>0 距离门不拦).
    只有 high<round(limit_price,2) 能拦. 验证 rounding 修复 (未round会把封板误判未封板)."""
    from a_stock.strategies import runner
    from a_stock.strategies.near_limit_up import NearLimitUp
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_rounded_seal_ohlcv())
    assert NearLimitUp().signals("T_600000", "A") == []


def _make_rounded_seal_ohlcv():
    """prev_close=10.03: unrounded 涨停价=11.033, rounded=11.03. high=11.03 触及=封板.
    close=11.02 (涨9.87%, dist_to_limit=0.13>0 → 距离门放行). 仅 rounding 能拦."""
    import pandas as pd
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    base = 10.03
    closes = [base] * (n - 1) + [11.02]
    opens = closes[:]
    opens[-1] = base
    highs = [c + 0.05 for c in closes[:-1]] + [11.03]  # 末根 high = rounded 涨停价 (触及=封板)
    lows = [c - 0.05 for c in closes[:-1]] + [base]
    return pd.DataFrame({"date": dates, "open": opens, "high": highs,
                         "low": lows, "close": closes, "volume": [10000] * n})


def test_near_limit_up_miss_low_gain(monkeypatch):
    """涨5% → 不触发 (需>7%)."""
    from a_stock.strategies import runner
    from a_stock.strategies.near_limit_up import NearLimitUp
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_limit_ohlcv(change_pct=5.0))
    assert NearLimitUp().signals("T_600000", "A") == []


def _make_limit_ohlcv(change_pct: float):
    """末根日内涨幅 = change_pct (close/open-1). 70根.
    NOTE: build_indicators.change_pct = (close-prev_close)/prev_close.
    构造使 prev_close==open (前根收=open), 这样 change_pct ≈ change_pct 参数."""
    import pandas as pd
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    # 前 n-1 根平稳, 末根 prev_close=10.0, last_close=10.0*(1+change_pct/100)
    base = 10.0
    closes = [base] * (n - 1) + [base * (1 + change_pct / 100)]
    opens = closes[:]
    opens[-1] = base  # open = prev_close, 使 body_pct = change_pct, change_pct = 涨跌幅
    highs = [max(o, c) + 0.05 for o, c in zip(opens, closes)]
    lows = [min(o, c) - 0.05 for o, c in zip(opens, closes)]
    return pd.DataFrame({"date": dates, "open": opens, "high": highs,
                         "low": lows, "close": closes, "volume": [10000] * n})


def test_moneyflow_surge_hit_top10(monkeypatch):
    """资金流排名 #5 + 收涨 → 触发 0.6."""
    from a_stock.strategies import runner
    from a_stock.strategies.moneyflow_surge import MoneyflowSurge
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_rising_ohlcv())
    mfs = MoneyflowSurge()
    mfs._rank = {"T_001": 5}
    sigs = mfs.signals("T_001", "A")
    assert len(sigs) == 1
    assert sigs[0].confidence == 0.6


def test_moneyflow_surge_miss_rank_too_low(monkeypatch):
    """排名 #15 (>10) → 不触发."""
    from a_stock.strategies import runner
    from a_stock.strategies.moneyflow_surge import MoneyflowSurge
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_rising_ohlcv())
    mfs = MoneyflowSurge()
    mfs._rank = {"T_001": 15}
    assert mfs.signals("T_001", "A") == []


def test_moneyflow_surge_miss_dropping(monkeypatch):
    """排名 #3 但收跌 → 不触发."""
    from a_stock.strategies import runner
    from a_stock.strategies.moneyflow_surge import MoneyflowSurge
    runner.clear_cache()
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_falling_ohlcv())
    mfs = MoneyflowSurge()
    mfs._rank = {"T_001": 3}
    assert mfs.signals("T_001", "A") == []


def _make_rising_ohlcv():
    import pandas as pd
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    closes = [10.0 + i * 0.01 for i in range(n - 1)] + [11.0]
    opens = closes[:]
    opens[-1] = 10.5  # 收涨
    return pd.DataFrame({"date": dates, "open": opens, "high": [c+0.1 for c in closes],
                         "low": [c-0.1 for c in closes], "close": closes,
                         "volume": [10000]*n})


def _make_falling_ohlcv():
    import pandas as pd
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    closes = [11.0 - i * 0.01 for i in range(n - 1)] + [10.0]
    opens = closes[:]
    opens[-1] = 10.5  # 收跌 (close 10 < open 10.5)
    return pd.DataFrame({"date": dates, "open": opens, "high": [c+0.1 for c in closes],
                         "low": [c-0.1 for c in closes], "close": closes,
                         "volume": [10000]*n})


def test_sector_momentum_hit(monkeypatch):
    """verdict=持续主线 + 候选涨4% → 触发 0.5."""
    from a_stock.strategies import runner
    from a_stock.strategies import sector_momentum as sm
    from a_stock.strategies.sector_momentum import SectorMomentum
    runner.clear_cache()
    # mock sector_rotation.analyze
    class FakeSR:
        strongest_repeat_name = "半导体"
        verdict = "持续主线"
    monkeypatch.setattr(sm, "_analyze", lambda: FakeSR())
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_change_ohlcv(4.0))
    sigs = SectorMomentum().signals("T_001", "A")
    assert len(sigs) == 1
    assert sigs[0].confidence == 0.5


def test_sector_momentum_miss_no_mainline(monkeypatch):
    """verdict=轮动 (非持续主线) → 不触发."""
    from a_stock.strategies import runner
    from a_stock.strategies import sector_momentum as sm
    from a_stock.strategies.sector_momentum import SectorMomentum
    runner.clear_cache()
    class FakeSR:
        strongest_repeat_name = "半导体"
        verdict = "轮动"
    monkeypatch.setattr(sm, "_analyze", lambda: FakeSR())
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_change_ohlcv(4.0))
    assert SectorMomentum().signals("T_001", "A") == []


def test_sector_momentum_miss_low_change(monkeypatch):
    """持续主线但涨2% (<3) → 不触发."""
    from a_stock.strategies import runner
    from a_stock.strategies import sector_momentum as sm
    from a_stock.strategies.sector_momentum import SectorMomentum
    runner.clear_cache()
    class FakeSR:
        strongest_repeat_name = "半导体"
        verdict = "持续主线"
    monkeypatch.setattr(sm, "_analyze", lambda: FakeSR())
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_change_ohlcv(2.0))
    assert SectorMomentum().signals("T_001", "A") == []


def test_sector_momentum_no_rotation_data(monkeypatch):
    """analyze 返回 None → 不报错, []."""
    from a_stock.strategies import runner
    from a_stock.strategies import sector_momentum as sm
    from a_stock.strategies.sector_momentum import SectorMomentum
    runner.clear_cache()
    monkeypatch.setattr(sm, "_analyze", lambda: None)
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_change_ohlcv(4.0))
    assert SectorMomentum().signals("T_001", "A") == []


def _make_change_ohlcv(change_pct: float):
    """末根涨跌幅 = change_pct (close vs prev_close)."""
    import pandas as pd
    n = 70
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    base = 10.0
    closes = [base] * (n - 1) + [base * (1 + change_pct / 100)]
    opens = closes[:]
    opens[-1] = base
    return pd.DataFrame({"date": dates, "open": opens, "high": [c+0.1 for c in closes],
                         "low": [c-0.1 for c in closes], "close": closes,
                         "volume": [10000]*n})


def test_sector_momentum_matches_real_verdict_format(monkeypatch):
    """真实 sector_rotation 返回 '🔥 持续主线' (带emoji). 策略必须能匹配, 不能死代码."""
    from a_stock.strategies import runner
    from a_stock.strategies import sector_momentum as sm
    from a_stock.strategies.sector_momentum import SectorMomentum
    runner.clear_cache()
    class RealishSR:
        strongest_repeat_name = "半导体"
        verdict = "🔥 持续主线"   # 真实格式, 带 emoji 前缀
    monkeypatch.setattr(sm, "_analyze", lambda: RealishSR())
    monkeypatch.setattr(runner, "_load_ohlcv", lambda c: _make_change_ohlcv(4.0))
    sigs = SectorMomentum().signals("T_001", "A")
    assert len(sigs) == 1, "策略必须匹配带 emoji 的真实 verdict, 否则生产死代码"


# ===== code-review #1: 坏子类不崩整个 _scan =====

def test_registry_broken_subclass_does_not_crash_scan(monkeypatch):
    """abstract 中间基类 (无 META) 加进 _REGISTRY 候选 → _scan 不崩, _scanned=True, 好策略仍注册.

    复现 #1: 坏子类实例化抛 AttributeError(无 META)/TypeError(未实现 abstract)
    在 try 外会让 _scan 崩, _scanned 不置 True, get_all 反复重崩 → 全策略层静默禁用.
    """
    from a_stock.strategies import registry
    from a_stock.strategies.base import BaseStrategy, StrategyMeta
    import types as _types

    MODNAME = "test_fake_mod_for_crash"  # 不以 _ 开头 (否则被 _scan 跳过)

    # 坏子类: 无 META → inst.META.name 抛 AttributeError (复现 abstract 中间基类)
    class BrokenStrategy(BaseStrategy):
        def filter(self, code, name):
            return True
        def signals(self, code, name):
            return []
    BrokenStrategy.__module__ = f"a_stock.strategies.{MODNAME}"

    # 好子类
    class GoodStrategy(BaseStrategy):
        META = StrategyMeta("good_strategy_for_test", 0.5, "好策略")
        def filter(self, code, name):
            return True
        def signals(self, code, name):
            return []
    GoodStrategy.__module__ = f"a_stock.strategies.{MODNAME}"

    fake_mod = _types.ModuleType(f"a_stock.strategies.{MODNAME}")
    fake_mod.BrokenStrategy = BrokenStrategy
    fake_mod.GoodStrategy = GoodStrategy

    import pkgutil
    fake_iter = [("", MODNAME, False)]

    def fake_import_module(name, package=None):
        if name.endswith(MODNAME):
            return fake_mod
        raise ImportError(f"unexpected: {name}")

    monkeypatch.setattr(pkgutil, "iter_modules", lambda _p: iter(fake_iter))
    monkeypatch.setattr(registry.importlib, "import_module", fake_import_module)

    registry._scanned = False
    _REGISTRY_BEFORE = dict(registry._REGISTRY)
    try:
        # 不应抛
        registry._scan()
        # _scanned 必须置 True (即使坏子类炸)
        assert registry._scanned is True, "_scanned 必须置 True, 否则 get_all 反复重崩"
        # get_all 不抛, 返回 list
        all_st = registry.get_all()
        assert isinstance(all_st, list)
        # 好策略仍注册 (坏策略跳过)
        names = {st.META.name for st in all_st}
        assert "good_strategy_for_test" in names
        assert "broken" not in names  # 坏的没注册
    finally:
        # 还原 registry: 删测试残留, 重扫真实策略
        registry._REGISTRY.clear()
        registry._REGISTRY.update(_REGISTRY_BEFORE)
        registry._scanned = True


def test_registry_broken_subclass_get_all_idempotent_after_crash(monkeypatch):
    """#1 二次验证: 坏子类让首次 _scan 部分失败后, get_all() 不反复重崩 (因 _scanned 已 True)."""
    from a_stock.strategies import registry
    from a_stock.strategies.base import BaseStrategy, StrategyMeta
    import types as _types

    MODNAME = "test_fake_mod_for_idem"

    class BrokenNoMeta(BaseStrategy):
        # 无 META → inst.META.name 抛 AttributeError
        def filter(self, code, name):
            return True
        def signals(self, code, name):
            return []
    BrokenNoMeta.__module__ = f"a_stock.strategies.{MODNAME}"

    class GoodTwo(BaseStrategy):
        META = StrategyMeta("good_two_for_test", 0.4, "好策略2")
        def filter(self, code, name):
            return True
        def signals(self, code, name):
            return []
    GoodTwo.__module__ = f"a_stock.strategies.{MODNAME}"

    fake_mod = _types.ModuleType(f"a_stock.strategies.{MODNAME}")
    fake_mod.BrokenNoMeta = BrokenNoMeta
    fake_mod.GoodTwo = GoodTwo

    import pkgutil
    fake_iter = [("", MODNAME, False)]

    def fake_import_module(name, package=None):
        if name.endswith(MODNAME):
            return fake_mod
        raise ImportError(f"unexpected: {name}")

    monkeypatch.setattr(pkgutil, "iter_modules", lambda _p: iter(fake_iter))
    monkeypatch.setattr(registry.importlib, "import_module", fake_import_module)

    registry._scanned = False
    _REGISTRY_BEFORE = dict(registry._REGISTRY)
    try:
        registry._scan()
        assert registry._scanned is True
        # 二次调 get_all 不重扫 (因 _scanned=True), 也不抛
        st1 = registry.get_all()
        st2 = registry.get_all()
        assert isinstance(st1, list) and isinstance(st2, list)
        names = {s.META.name for s in st2}
        assert "good_two_for_test" in names
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(_REGISTRY_BEFORE)
        registry._scanned = True
