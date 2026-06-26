"""板块聚合:行业/概念/热点/龙虎榜。"""
from typing import Any
from a_stock.a_stock_data import industry_comparison, ths_hot_reason, daily_dragon_tiger


def scan_sectors(trade_date: str) -> dict[str, Any]:
    # industry_comparison 返回: {"top": [...], "bottom": [...], "total": int}
    # top → industry, bottom → concept
    ic = industry_comparison(top_n=30)
    return {
        "industry":    ic.get("top", []),
        "concept":     ic.get("bottom", []),
        "hot":         _safe_ths_hot(trade_date),
        "dragon_tiger": daily_dragon_tiger(trade_date).get("data", []),
    }


def _safe_ths_hot(trade_date: str):
    try:
        df = ths_hot_reason(trade_date)
        return df.to_dict("records") if hasattr(df, "to_dict") else list(df)
    except Exception:
        return []