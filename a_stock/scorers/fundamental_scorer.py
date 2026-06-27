"""基本面评分 (10%): 净利同比/ROE/OCF 分档.
抄 KHunter fundamental_scorer.py:309 三项分档形态."""
from . import FactorScore


def score(code: str) -> FactorScore:
    """基本面分档. base 50."""
    try:
        from a_stock.a_stock_data import financials
        fin = financials.get_financials(code) if hasattr(financials, "get_financials") else {}
    except Exception:
        return FactorScore(score=50, detail={"reason": "财报拉取失败"})

    if not fin:
        return FactorScore(score=50, detail={"reason": "无财报数据"})

    s = 50
    detail = {}

    # 净利同比
    ni_grow = fin.get("net_profit_yoy") or fin.get("净利润同比") or 0
    if ni_grow > 30:
        s += 20
        detail["ni_grow"] = f"+{ni_grow:.0f}% 高增"
    elif ni_grow > 0:
        s += 10
        detail["ni_grow"] = f"+{ni_grow:.0f}%"
    elif ni_grow > -20:
        s -= 10
        detail["ni_grow"] = f"{ni_grow:.0f}%"
    else:
        s -= 20
        detail["ni_grow"] = f"{ni_grow:.0f}% 大降"

    # ROE
    roe = fin.get("roe") or fin.get("净资产收益率") or 0
    if roe > 15:
        s += 20
        detail["roe"] = f"{roe:.1f}% 优"
    elif roe > 5:
        s += 10
        detail["roe"] = f"{roe:.1f}%"
    elif roe > 0:
        s += 0
        detail["roe"] = f"{roe:.1f}%"
    else:
        s -= 20
        detail["roe"] = f"{roe:.1f}% 负"

    # 注: KHunter 基本面 veto 是死代码 (净利<-50%/ROE<-5%), 这里也不启用 veto
    # 基本面差靠低分自然淘汰, 不一票否决 (避免错杀周期股底部)

    return FactorScore(score=s, detail=detail)
