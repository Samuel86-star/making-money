"""板块评分 (10%): 当日板块排名.
抄 KHunter sector_scorer.py:664 形态, 简化."""
from . import FactorScore


def score(code: str) -> FactorScore:
    """板块排名分档. base 50. 注: KHunter 板块veto是死代码, 不抄."""
    try:
        from a_stock.a_stock_data import eastmoney_concept_blocks
        blocks = eastmoney_concept_blocks(code)
    except Exception:
        return FactorScore(score=50, detail={"reason": "板块拉取失败"})

    if not blocks or not blocks.get("industries"):
        return FactorScore(score=50, detail={"reason": "无板块数据"})

    industry = blocks["industries"][0].get("name", "")
    detail = {"industry": industry}

    # 简化: 有板块信息给基础分, 实际板块涨跌排名需 sector_scan 数据
    # TODO Phase4: 接 sector_rotation 持续性加强
    s = 50
    return FactorScore(score=s, detail=detail)
