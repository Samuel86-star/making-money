"""板块聚合:行业/概念/热点/龙虎榜。"""
from typing import Any
from py.a_stock_data import industry_comparison, ths_hot_reason, daily_dragon_tiger


def scan_sectors(trade_date: str) -> dict[str, Any]:
    # industry_comparison 返回结构需在实施时对齐 SKILL.md 1209-1257
    # 预期: {"industry": [{name, change_pct, net_flow, ...}], "concept": [...]}
    # 若实际是 {"data": [...]},需调整下面 .get 调用
    ic = industry_comparison(top_n=30)
    return {
        "industry":    ic.get("industry", []),
        "concept":     ic.get("concept", []),
        "hot":         _safe_ths_hot(trade_date),
        "dragon_tiger": daily_dragon_tiger(trade_date).get("data", []),
    }


def _safe_ths_hot(trade_date: str):
    try:
        df = ths_hot_reason(trade_date)
        return df.to_dict("records") if hasattr(df, "to_dict") else list(df)
    except Exception:
        return []