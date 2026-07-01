"""signal_backtest 单元测试.
验证滑动窗口forward-return测量 + 聚合统计 + base rate对比.
用trivial signal_fn (lambda) 测机制, 不依赖真实detector."""
from a_stock.signal_backtest import backtest_signal, aggregate_stats, base_rate, edge


# === 单股滑动回测 ===

def test_flat_series_zero_forward_return():
    """平价序列 + always-true signal → 所有forward return=0."""
    closes = [10.0] * 20
    vols = [1000] * 20
    r = backtest_signal(lambda c, v: True, closes, vols, forward_days=(5,), min_history=5)
    assert len(r[5]) > 0
    assert all(abs(x) < 1e-9 for x in r[5])


def test_rising_series_all_positive_forward():
    """上升序列 (close[i]=i) + always-true → 所有forward return>0, 胜率1.0."""
    closes = [float(i) for i in range(1, 25)]  # 1..24
    vols = [1000] * 24
    r = backtest_signal(lambda c, v: True, closes, vols, forward_days=(5,), min_history=5)
    assert all(x > 0 for x in r[5])


def test_signal_never_fires_empty_result():
    """signal永False → 空结果."""
    closes = [10.0] * 20
    r = backtest_signal(lambda c, v: False, closes, [1000]*20, forward_days=(5,), min_history=5)
    assert r[5] == []


def test_min_history_respected():
    """T从min_history起, 之前不跑. n=20, N=5 → T range(15,15) 空."""
    closes = [10.0] * 20
    r = backtest_signal(lambda c, v: True, closes, [1000]*20, forward_days=(5,), min_history=15)
    assert r[5] == []  # range(15, 20-5)=range(15,15) 空


def test_forward_return_value_correct():
    """具体forward return数值: T=5 entry=10, close[10]=12 → +20%."""
    closes = [10.0]*6 + [12.0]*14  # index0-5=10, index6+ =12
    # signal: close[-1]>10 → 只在T>=6触发; T=6 entry=12, 全程12 → 0%
    # 换signal: close[-1]==10 → T in 0..5; 但min_history=5 → T=5 entry=10, close[10]=12 → +20%
    r = backtest_signal(lambda c, v: c[-1] == 10, closes, [1000]*20,
                        forward_days=(5,), min_history=5)
    # T=5 唯一命中 (T<5 min_history挡, T>5 close变12不命中)
    assert len(r[5]) == 1
    assert abs(r[5][0] - 0.2) < 1e-9  # +20%


def test_insufficient_forward_skipped():
    """T+forward越界 → 该T跳过, 不崩."""
    closes = [10.0] * 8  # 太短, T=5, N=5 → T+5=10>8 越界
    r = backtest_signal(lambda c, v: True, closes, [1000]*8, forward_days=(5,), min_history=5)
    assert r[5] == []


def test_exception_in_signal_treated_as_not_fired():
    """signal_fn抛异常 → 当未命中, 不崩."""
    def boom(c, v):
        raise RuntimeError("detector err")
    r = backtest_signal(boom, [10.0]*20, [1000]*20, forward_days=(5,), min_history=5)
    assert r[5] == []


# === 聚合统计 ===

def test_aggregate_win_rate_and_avg():
    """合并多股, 算胜率/均值."""
    per_stock = [
        {5: [0.05, -0.02, 0.03]},   # 2 win / 3
        {5: [0.10, -0.08]},          # 1 win / 2
    ]
    stats = aggregate_stats(per_stock, forward_days=(5,))
    s = stats[5]
    assert s["count"] == 5
    assert s["wins"] == 3
    assert abs(s["win_rate"] - 0.6) < 1e-9
    assert abs(s["avg_return"] - 0.016) < 1e-9  # (0.05-0.02+0.03+0.10-0.08)/5


def test_aggregate_empty_returns_none():
    stats = aggregate_stats([{5: []}], forward_days=(5,))
    assert stats[5] is None


# === base rate + edge ===

def test_base_rate_all_days():
    """base rate = always-true signal 的forward return均值 (全市场基准)."""
    closes = [float(i) for i in range(1, 25)]  # 上升
    br = base_rate(closes, [1000]*24, forward_days=(5,), min_history=5)
    assert br[5] is not None
    assert br[5]["avg_return"] > 0


def test_edge_signal_vs_base():
    """edge = signal_avg - base_avg. 信号优于base → edge>0."""
    closes = [float(i) for i in range(1, 25)]
    # signal: 只在close>15时True (后段涨得更陡?) — 此序列线性, signal≈base
    sig = backtest_signal(lambda c, v: c[-1] > 15, closes, [1000]*24,
                          forward_days=(5,), min_history=5)
    br = base_rate(closes, [1000]*24, forward_days=(5,), min_history=5)
    sig_avg = sum(sig[5])/len(sig[5]) if sig[5] else 0
    br_avg = br[5]["avg_return"]
    e = edge(sig_avg, br_avg)
    assert isinstance(e, float)


# === 止损建模 (突破型信号median负, 实战有止损, 满horizon不止损=低估) ===

from a_stock.signal_backtest import realized_return_with_stop, backtest_signal as _bs


def test_stop_triggered_caps_loss():
    """任意日low触止损 → return=-stop_pct (封顶亏损)."""
    entry = 10.0
    highs = [10.5, 9.8, 10.2, 10.3, 10.4]
    lows =  [10.0, 9.5, 10.0, 10.1, 10.2]   # day2(索引1) low9.5<9.7
    closes = [10.3, 9.6, 10.1, 10.2, 10.3]
    r = realized_return_with_stop(entry, highs, lows, closes, stop_pct=0.03, N=5)
    assert abs(r - (-0.03)) < 1e-9


def test_stop_not_triggered_holds_to_horizon():
    """未触止损 → 持有到N日收盘的forward return."""
    entry = 10.0
    highs = [10.5]*5
    lows =  [9.9]*5   # 全程 > 9.7 不触发
    closes = [10.1, 10.2, 10.3, 10.4, 10.5]
    r = realized_return_with_stop(entry, highs, lows, closes, stop_pct=0.03, N=5)
    assert abs(r - 0.05) < 1e-9


def test_stop_uses_low_not_close():
    """日内low触止损, 即使收盘回升 → 仍止损出场 (用low判)."""
    entry = 10.0
    highs = [10.5, 10.0, 10.5, 10.5, 10.5]
    lows =  [10.0, 9.6, 9.9, 9.9, 9.9]   # day2 low9.6<9.7 触发
    closes = [10.3, 10.2, 10.5, 10.5, 10.5]
    r = realized_return_with_stop(entry, highs, lows, closes, stop_pct=0.03, N=5)
    assert abs(r - (-0.03)) < 1e-9


def test_stop_insufficient_data_returns_none():
    """forward数据不足N日 → None (跳过)."""
    r = realized_return_with_stop(10.0, [10.5]*2, [9.9]*2, [10.1]*2, 0.03, N=5)
    assert r is None


def test_backtest_with_stop_changes_results():
    """带stop_pct 与 不带stop 结果不同 (止损路径生效)."""
    closes = [10.0]*5 + [10.5, 11.0, 9.0, 8.0, 7.0]  # T=4 entry10, 后续急跌
    highs =  [10.0]*5 + [10.6, 11.1, 9.2, 8.2, 7.2]
    lows =   [10.0]*5 + [10.4, 10.9, 8.9, 7.9, 6.9]
    vols = [1000]*10
    r_nostop = _bs(lambda c, v: True, closes, vols, forward_days=(5,), min_history=4)
    r_stop = _bs(lambda c, v: True, closes, vols, forward_days=(5,), min_history=4,
                 stop_pct=0.03, highs=highs, lows=lows)
    assert r_nostop[5] and r_stop[5]
    assert r_stop[5][0] == -0.03       # 止损封顶 -3%
    assert r_nostop[5][0] < -0.03      # 无止损更惨


def test_backtest_stop_without_highlow_falls_back():
    """stop_pct给但highs/lows缺 → 回退无止损模式 (不崩)."""
    closes = [10.0]*10
    r = _bs(lambda c, v: True, closes, [1000]*10, forward_days=(5,),
            min_history=4, stop_pct=0.03)
    assert len(r[5]) > 0

