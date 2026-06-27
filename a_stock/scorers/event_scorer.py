"""事件评分 (10%): ST/暴雷/减持.
抄 KHunter event_scorer.py:819 形态, 简化. 只抄3类真veto之一:事件."""
from . import FactorScore


def score(code: str, name: str = "") -> FactorScore:
    """事件分档. base 50. veto: ST/暴雷."""
    s = 50
    detail = {}
    n = (name or "").upper()

    # ST 一票否决
    if "ST" in n or "*ST" in n:
        return FactorScore(score=0, veto=True, veto_reason="ST股",
                           detail={"event": "ST"})

    # 业绩暴雷 veto (需预报数据, 简化: 留接口)
    # TODO: 接 forecast 数据, 预减且<-80% → veto

    return FactorScore(score=s, detail=detail)
