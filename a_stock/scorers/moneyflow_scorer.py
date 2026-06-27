"""资金面评分 (35%): 5日主力净流分档.
抄 KHunter moneyflow_scorer.py:513 分档step形态, 简化."""
from . import FactorScore
from a_stock.a_stock_data import stock_fund_flow_120d


def score(code: str) -> FactorScore:
    """5日主力净流分档. base 50."""
    try:
        flows = stock_fund_flow_120d(code)
    except Exception:
        return FactorScore(score=50, detail={"reason": "资金流拉取失败"})

    if not flows:
        return FactorScore(score=50, detail={"reason": "无资金流数据"})

    # 近5日主力净流 (元)
    net_5d = sum(r.get("main", 0) for r in flows[:5])
    net_yi = net_5d / 1e8  # 转亿

    s = 50
    detail = {"net_5d_yi": round(net_yi, 2)}

    # 分档 (抄 KHunter _score_main_net_flow 形态, 阈值适配)
    if net_yi > 1.0:
        s = 90
        detail["level"] = "大幅净流入"
    elif net_yi > 0.5:
        s = 75
        detail["level"] = "净流入"
    elif net_yi > 0.01:
        s = 60
        detail["level"] = "小幅净流入"
    elif net_yi > -0.01:
        s = 50
        detail["level"] = "均衡"
    elif net_yi > -0.5:
        s = 35
        detail["level"] = "小幅净流出"
    elif net_yi > -1.0:
        s = 20
        detail["level"] = "净流出"
    else:
        s = 10
        detail["level"] = "大幅净流出"

    # veto: 5日净流 < -1亿 (出货信号)
    if net_yi < -1.0:
        return FactorScore(score=s, veto=True,
                           veto_reason=f"5日主力净流{net_yi:.2f}亿<-1亿(出货)",
                           detail=detail)

    return FactorScore(score=s, detail=detail)
