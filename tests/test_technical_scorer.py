"""technical_scorer 单元测试. T_ 前缀 mock ohlcv, 不碰真实 parquet.
重点测 P1: 量价验证 (volume 已加载但历史未用)."""
from unittest.mock import patch
from a_stock.scorers import technical_scorer


def _rows(closes, vols):
    """造 OHLCV rows (close=给定, volume=给定, 其余凑数)."""
    return [{"date": f"2026-01-{i+1:02d}", "open": c, "high": c, "low": c,
             "close": c, "volume": v} for i, (c, v) in enumerate(zip(closes, vols))]


def _series(base, n, tail):
    """造 n 长度 close 序列: 前 n-len(tail) 个=base, 尾部=tail."""
    return [base] * (n - len(tail)) + list(tail)


def _patch_load(rows):
    return patch.object(technical_scorer, "_load_ohlcv", return_value=rows)


# === 量价验证 (核心新增) ===

def test_volume_breakout_adds_score():
    """放量突破前高 (量比>=1.5 且 价破近20日高) → +10."""
    closes = _series(10.0, 40, [11.5])  # 前39日10, 末日突破
    vols = [1000] * 39 + [2000]          # 量比2.0
    with _patch_load(_rows(closes, vols)):
        fs = technical_scorer.score("T_VOL1")
    assert fs.detail.get("vol_breakout") == "放量突破"
    # 基础多头/MA分 + 量价+10
    assert fs.score > 50


def test_shrink_rise_divergence_deducts():
    """缩量上涨 (价升 量比<0.7) → -8 背离."""
    closes = [10.0 * (1 + 0.001 * i) for i in range(40)]
    closes[-1] = closes[-2] * 1.01  # 末日升
    vols = [1000] * 39 + [600]      # 量比0.6
    with _patch_load(_rows(closes, vols)):
        fs = technical_scorer.score("T_VOL2")
    assert fs.detail.get("vol_divergence") == "价升量缩"


def test_shrink_breakdown_is_washout():
    """缩量破位 (价跌 量比<0.8) → +5 洗盘信号 (反向加分)."""
    closes = _series(10.0, 40, [9.8, 9.5])  # 末两日下跌
    vols = [1000] * 39 + [700]              # 末日量比0.7
    with _patch_load(_rows(closes, vols)):
        fs = technical_scorer.score("T_VOL3")
    assert fs.detail.get("vol_breakdown") == "缩量洗盘"


def test_volume_breakdown_deducts():
    """放量破位 (量比>=1.5 且 价跌) → -10 真破位."""
    closes = _series(10.0, 40, [9.8, 9.0])
    vols = [1000] * 39 + [2000]
    with _patch_load(_rows(closes, vols)):
        fs = technical_scorer.score("T_VOL4")
    assert fs.detail.get("vol_breakdown") == "放量破位"


def test_no_volume_data_does_not_crash():
    """volume 全 None 不崩溃, 量价分跳过."""
    rows = [{"date": f"2026-01-{i+1:02d}", "open": 10, "high": 10, "low": 10,
             "close": 10, "volume": None} for i in range(40)]
    with _patch_load(rows):
        fs = technical_scorer.score("T_VOL5")
    assert "vol_breakout" not in fs.detail
    assert "vol_divergence" not in fs.detail


# === 回踩买点 (MA10 + 多头排列) ===

def test_pullback_to_ma5_in_uptrend_detected():
    """多头排列 + 价回踩MA5(±1.5%)不破 → 标记回踩买点."""
    # 构造多头上升序列, 共65日(够ma60), 末日小回调到MA5附近
    base = [10.0 + i * 0.1 for i in range(65)]  # 10.0→16.4 上升
    base[-1] = base[-2] * 0.995  # 末日微跌回踩
    closes = base
    vols = [1000] * 65
    with _patch_load(_rows(closes, vols)):
        fs = technical_scorer.score("T_PULL1")
    assert fs.detail.get("pullback_buy") == "回踩MA5"


def test_pullback_not_triggered_when_far_above_ma():
    """价远离MA5(急拉) → 不标回踩买点."""
    # 65天多头上升序列(够ma60), 末日急拉8%远离MA5
    base = [10.0 + i * 0.1 for i in range(65)]  # 10.0→16.4
    base[-1] = base[-2] * 1.08  # 末日急拉8%, 价远离MA5(>1.5%)
    closes = base
    vols = [1000] * 65
    with _patch_load(_rows(closes, vols)):
        fs = technical_scorer.score("T_PULL2")
    assert "pullback_buy" not in fs.detail


def test_pullback_not_triggered_in_downtrend():
    """空头排列 → 不标回踩买点(无多头基础)."""
    # 65天空头序列(够ma60), price<ma5<ma20<ma60
    closes = [20.0 - i * 0.15 for i in range(65)]  # 20.0→10.25 下降
    vols = [1000] * 65
    with _patch_load(_rows(closes, vols)):
        fs = technical_scorer.score("T_PULL3")
    assert "pullback_buy" not in fs.detail
