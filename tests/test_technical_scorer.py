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


# === VCP 量化 (Minervini SEPA, A股适配, 强化 [A] 假设) ===

def _vcp_series():
    """90日: 前50上升建立趋势, 末40日收缩(左宽→右窄)+缩量."""
    closes = [10.0 + i * 0.09 for i in range(50)]  # 10.0→14.41 上升
    left = [14.5, 15.5, 14.0, 15.3, 13.8, 15.0, 14.2, 15.4, 13.9, 15.1, 14.0, 15.2, 14.3]
    mid = [15.0, 15.6, 14.9, 15.5, 15.0, 15.4, 14.8, 15.3, 15.0, 15.5, 14.9, 15.2, 15.0]
    right = [15.1, 15.3, 15.0, 15.2, 15.1, 15.3, 15.2, 15.0, 15.2, 15.1, 15.3, 15.2, 15.1, 15.25]
    closes = closes + left + mid + right  # 50+13+13+14=90
    vols = [2000] * 50 + [2000] * 13 + [1200] * 13 + [600] * 14  # 左高右低=缩量
    return closes, vols


def test_vcp_full_pattern_detected():
    """完整VCP(趋势+收缩+缩量) → _detect_vcp 返回 dict, contractions≥2, vol_dryup=True."""
    closes, vols = _vcp_series()
    vcp = technical_scorer._detect_vcp(closes, vols)
    assert vcp is not None
    assert vcp["contractions"] >= 2
    assert vcp["vol_dryup"] is True
    assert vcp["left_range"] > vcp["mid_range"] > vcp["right_range"]


def test_vcp_scoring_full_adds_12():
    """完整VCP → score +12, detail 标 vcp_setup."""
    closes, vols = _vcp_series()
    with _patch_load(_rows(closes, vols)):
        fs = technical_scorer.score("T_VCP1")
    assert fs.detail.get("vcp_setup", "").startswith("VCP完整")
    # 对比无VCP序列分数应更高 (用末段不收缩的对照)


def test_vcp_rejected_in_downtrend():
    """下降趋势 → 趋势模板不满足 → None."""
    closes = [20.0 - i * 0.1 for i in range(90)]  # 下降
    vols = [1000] * 90
    assert technical_scorer._detect_vcp(closes, vols) is None


def test_vcp_rejected_expanding_ranges():
    """末段范围扩大(非收缩) → None."""
    closes, _ = _vcp_series()
    # 把末段改成扩大震荡
    closes[-14:] = [15.0, 15.5, 14.8, 15.8, 14.5, 16.0, 14.2, 16.2, 14.0, 16.5, 13.8, 16.8, 13.5, 17.0]
    vols = [1000] * 90
    vcp = technical_scorer._detect_vcp(closes, vols)
    assert vcp is None


def test_vcp_partial_no_dryup_still_detected():
    """收缩满足但量没缩 → 检出 VCP, vol_dryup=False (部分VCP, +6)."""
    closes, _ = _vcp_series()
    vols = [1000] * 90  # 均量, 无缩量
    vcp = technical_scorer._detect_vcp(closes, vols)
    assert vcp is not None
    assert vcp["vol_dryup"] is False


def test_vcp_rejected_short_history():
    """<60日 → None (数据不足)."""
    closes = [10.0 + i * 0.1 for i in range(50)]
    vols = [1000] * 50
    assert technical_scorer._detect_vcp(closes, vols) is None
