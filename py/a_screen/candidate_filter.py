"""初筛 + 评分(短线/中线)。"""
import py.config as cfg


def initial_filter(stocks: list[dict], strategy: str) -> list[dict]:
    if strategy == "short":
        return [
            s for s in stocks
            if s.get("net_flow", 0) > 0
            and 0 <= s.get("change_pct", 0) <= 7
        ]
    elif strategy == "mid":
        return [
            s for s in stocks
            if 0 < s.get("pe_ttm", 0) <= 50
            and s.get("mcap_yi", 0) >= 50
        ]
    return []


def score_candidate(c: dict, strategy: str, sector_data: dict) -> float:
    """返回 0-100 评分。"""
    weights = cfg.SCORING[strategy]
    if strategy == "short":
        return _score_short(c, weights, sector_data)
    return _score_mid(c, weights)


def _score_short(c, w, sector_data) -> float:
    s = 0.0
    # net_flow_rank:用 net_flow 简单归一化(>1e8 = 满分)
    nf = c.get("net_flow", 0) or 0
    s += min(nf / 1e8, 1.0) * w["net_flow_rank"]
    # change_pct_band:1-5% 最优
    pct = c.get("change_pct", 0) or 0
    if 1 <= pct <= 5:
        s += w["change_pct_band"]
    elif 0 <= pct < 1 or 5 < pct <= 7:
        s += w["change_pct_band"] * 0.5
    # sector_alignment:是否在强势板块
    align = c.get("sector_alignment", 0) or 0
    s += min(align, 1.0) * w["sector_alignment"]
    # report_count_7d:研报热度(0-10 归一)
    rc = c.get("report_count_7d", 0) or 0
    s += min(rc / 10, 1.0) * w["report_count_7d"]
    # hot_reason_hit
    if c.get("hot_reason_hit"):
        s += w["hot_reason_hit"]
    return min(s, 100.0)


def _score_mid(c, w) -> float:
    s = 0.0
    # valuation:PE 0-30 线性,>30 衰减
    pe = c.get("pe_ttm", 0) or 0
    if 0 < pe <= 30:
        s += w["valuation"]
    elif 30 < pe <= 50:
        s += w["valuation"] * (50 - pe) / 20
    # fund_flow_20d
    ff = c.get("fund_flow_20d", 0) or 0
    s += min(ff / 5e8, 1.0) * w["fund_flow_20d"]
    # report_coverage
    rc = c.get("report_count_30d", 0) or 0
    s += min(rc / 20, 1.0) * w["report_coverage"]
    # theme_catalyst(0-1)
    s += min(c.get("theme_catalyst", 0) or 0, 1.0) * w["theme_catalyst"]
    # tech_position(0-1)
    s += min(c.get("tech_position", 0) or 0, 1.0) * w["tech_position"]
    return min(s, 100.0)