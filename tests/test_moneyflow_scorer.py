"""moneyflow_scorer 单元测试.
重点: 超大单(super_zhuan) + 资金加速 + 量价背离 (个股级[J]派发).
mock stock_fund_flow_120d, 不碰网络. T_ 前缀假 code."""
from unittest.mock import patch
from a_stock.scorers import moneyflow_scorer


def _flow(main=0.0, super_=0.0, big=None, days=5):
    """造 days 条资金流记录 (单位: 元). main/super 单日值."""
    if big is None:
        big = main - super_  # 自洽: main = super + big
    return [{"date": f"2026-06-{20+i}", "main": main, "super": super_,
             "big": big, "medium": 0.0, "small": 0.0, "main_pct": 0.0}
            for i in range(days)]


def _patch(flows):
    return patch.object(moneyflow_scorer, "stock_fund_flow_120d", return_value=flows)


def _patch_closes(closes=None):
    return patch.object(moneyflow_scorer, "_load_closes", return_value=closes or [])


# === main 5日 level (原有分档不回归) ===

def test_main_large_inflow_scores_90():
    """主力5日净流>1亿 → 90."""
    flows = _flow(main=0.3e8, days=5)  # 5×0.3=1.5亿
    with _patch(flows), _patch_closes():
        fs = moneyflow_scorer.score("T_MF1")
    assert fs.score == 90
    assert fs.detail["level"] == "大幅净流入"


def test_main_heavy_outflow_veto():
    """主力5日净流<-1亿 → veto=True (出货)."""
    flows = _flow(main=-0.3e8, days=5)  # -1.5亿
    with _patch(flows), _patch_closes():
        fs = moneyflow_scorer.score("T_MF2")
    assert fs.veto is True
    assert "出货" in fs.veto_reason


def test_empty_flows_neutral():
    """无数据 → 50."""
    with _patch([]), _patch_closes():
        fs = moneyflow_scorer.score("T_MF3")
    assert fs.score == 50


# === 超大单 super_zhuan (smart money, 新增) ===

def test_super_zhuan_large_inflow_bonus():
    """超大单5日>0.5亿 → +8."""
    flows = _flow(main=0.2e8, super_=0.15e8, days=5)  # main 1亿(60分档), super 0.75亿
    with _patch(flows), _patch_closes():
        fs = moneyflow_scorer.score("T_MF4")
    assert fs.detail.get("super_signal") == "超大单大幅净入"
    assert fs.score > 60  # 60分档 + 8


def test_super_zhuan_large_outflow_penalty():
    """超大单5日<-0.5亿 → -8."""
    flows = _flow(main=-0.05e8, super_=-0.15e8, days=5)  # super -0.75亿
    with _patch(flows), _patch_closes():
        fs = moneyflow_scorer.score("T_MF5")
    assert fs.detail.get("super_signal") == "超大单大幅净出"


def test_super_missing_does_not_crash():
    """资金流无 super 字段 (旧数据) → 不崩, super_5d=0."""
    flows = [{"date": f"2026-06-{20+i}", "main": 0.2e8} for i in range(5)]
    with _patch(flows), _patch_closes():
        fs = moneyflow_scorer.score("T_MF6")
    assert "super_signal" not in fs.detail  # super 0, 不触发信号


# === 资金加速 (3d vs 5d 日均) ===

def test_acceleration_bonus():
    """近3日日均 > 5日日均×1.3 且为正 → 资金加速流入 +5."""
    # flows[0]=最近日. 近3日(前3条)大额, 前2日(4-5条)小额 → 3d日均>5d日均
    flows = [{"date": f"2026-06-{24-i}", "main": 0.2e8, "super": 0, "big": 0.2e8} for i in range(3)]
    flows += [{"date": f"2026-06-{21-i}", "main": 0.01e8, "super": 0, "big": 0.01e8} for i in range(2)]
    with _patch(flows), _patch_closes():
        fs = moneyflow_scorer.score("T_MF7")
    assert fs.detail.get("accel") == "资金加速流入"


# === 量价背离 (个股级 [J] 派发/吸筹) ===

def test_divergence_price_up_main_out_distribution():
    """价升5日>3% 但主力流出 → 派发嫌疑 -10."""
    flows = _flow(main=-0.1e8, days=5)  # main -0.5亿 (>-1亿不veto)
    closes = [10.0, 10.1, 10.2, 10.3, 10.4, 10.5]  # +5% (close[-1] vs close[-6])
    with _patch(flows), _patch_closes(closes):
        fs = moneyflow_scorer.score("T_MF8")
    assert fs.detail.get("divergence") == "价升主力流出(派发嫌疑)"


def test_divergence_price_down_main_in_accumulation():
    """价跌5日>3% 但主力流入 → 吸筹嫌疑 +6."""
    flows = _flow(main=0.1e8, days=5)  # main 0.5亿
    closes = [10.5, 10.4, 10.3, 10.2, 10.1, 10.0]  # -4.76%
    with _patch(flows), _patch_closes(closes):
        fs = moneyflow_scorer.score("T_MF9")
    assert fs.detail.get("divergence") == "价跌主力流入(吸筹嫌疑)"


def test_no_divergence_when_aligned():
    """价量同向 → 无背离标记."""
    flows = _flow(main=0.2e8, days=5)  # 流入
    closes = [10.0, 10.1, 10.2, 10.3, 10.4, 10.5]  # 价升
    with _patch(flows), _patch_closes(closes):
        fs = moneyflow_scorer.score("T_MF10")
    assert "divergence" not in fs.detail


# === 字段语义一致性 (交易日自检 main ≈ super+big) ===

def test_fund_flow_field_consistency_live():
    """真实数据自检: main 应 ≈ super+big (东财 主力=超大单+大单).
    非交易日/无数据 skip. 误差>20% 说明字段映射错, 需修 eastmoney.py."""
    import pytest
    from a_stock.a_stock_data import stock_fund_flow_120d
    flows = stock_fund_flow_120d("600276")
    if not flows:
        pytest.skip("无资金流数据 (非交易日/API不可达)")
    # 取最近5日, 逐日校验 main ≈ super+big
    for r in flows[:5]:
        main = r.get("main", 0)
        recon = r.get("super", 0) + r.get("big", 0)
        if main == 0:
            continue
        err = abs(main - recon) / abs(main)
        assert err < 0.20, f"字段不一致: main={main} vs super+big={recon} (err={err:.0%}), 查 eastmoney.py 字段映射"
