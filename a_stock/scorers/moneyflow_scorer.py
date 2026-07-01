"""资金面评分 (35%): 主力净流分档 + 超大单 + 资金加速 + 量价背离.
抄 KHunter moneyflow_scorer.py:513 分档step形态, 简化 + 扩展.

个股级 [J] 派发信号: 价升主力流出 = 出货嫌疑 (配合 Wyckoff UTAD).
超大单(super_zhuan)=smart money, 比 main 更早反映机构动作."""
from . import FactorScore
from a_stock.a_stock_data import stock_fund_flow_120d


def _load_closes(code: str, days: int = 10) -> list[float]:
    """加载近 N 日收盘价 (量价背离用). 无数据返回空."""
    try:
        import a_stock.ohlcv as ohlcv
        df = ohlcv.load_ohlcv(code)
        if len(df) == 0:
            return []
        col = "close" if "close" in df.columns else "Close"
        return df[col].astype(float).tolist()[-days:]
    except Exception:
        return []


def score(code: str) -> FactorScore:
    """资金面: main 5日分档 + 超大单 + 加速 + 背离. base 50."""
    try:
        flows = stock_fund_flow_120d(code)
    except Exception:
        return FactorScore(score=50, detail={"reason": "资金流拉取失败"})

    if not flows:
        return FactorScore(score=50, detail={"reason": "无资金流数据"})

    # 近5日主力净流 (元→亿)
    main_5d = sum(r.get("main", 0) for r in flows[:5])
    main_3d = sum(r.get("main", 0) for r in flows[:3])
    main_yi = main_5d / 1e8
    super_5d = sum(r.get("super", 0) for r in flows[:5]) / 1e8

    s = 50
    detail = {"main_5d_yi": round(main_yi, 2), "super_5d_yi": round(super_5d, 2)}

    # 1. main 5日分档 (原有, 不回归)
    if main_yi > 1.0:
        s = 90
        detail["level"] = "大幅净流入"
    elif main_yi > 0.5:
        s = 75
        detail["level"] = "净流入"
    elif main_yi > 0.01:
        s = 60
        detail["level"] = "小幅净流入"
    elif main_yi > -0.01:
        s = 50
        detail["level"] = "均衡"
    elif main_yi > -0.5:
        s = 35
        detail["level"] = "小幅净流出"
    elif main_yi > -1.0:
        s = 20
        detail["level"] = "净流出"
    else:
        s = 10
        detail["level"] = "大幅净流出"

    # 2. 超大单 smart money (5日净额 ±8/±4)
    if super_5d > 0.5:
        s += 8
        detail["super_signal"] = "超大单大幅净入"
    elif super_5d > 0.1:
        s += 4
        detail["super_signal"] = "超大单净入"
    elif super_5d < -0.5:
        s -= 8
        detail["super_signal"] = "超大单大幅净出"
    elif super_5d < -0.1:
        s -= 4
        detail["super_signal"] = "超大单净出"

    # 3. 资金加速 (3d 日均 vs 5d 日均, 动量)
    daily_5d = main_5d / 5
    daily_3d = main_3d / 3
    if daily_5d > 0 and daily_3d > daily_5d * 1.3:
        s += 5
        detail["accel"] = "资金加速流入"
    elif daily_5d < 0 and daily_3d < daily_5d * 0.7:
        s -= 5
        detail["accel"] = "资金减速/转出"

    # 4. 量价背离 (个股级 [J] 派发/吸筹, 用近6日收盘)
    closes = _load_closes(code)
    if len(closes) >= 6:
        price_chg = (closes[-1] - closes[-6]) / closes[-6]
        if price_chg > 0.03 and main_yi < -0.3:
            s -= 10
            detail["divergence"] = "价升主力流出(派发嫌疑)"
        elif price_chg < -0.03 and main_yi > 0.3:
            s += 6
            detail["divergence"] = "价跌主力流入(吸筹嫌疑)"

    # veto: 5日主力净流 < -1亿 (出货信号)
    if main_yi < -1.0:
        return FactorScore(score=s, veto=True,
                           veto_reason=f"5日主力净流{main_yi:.2f}亿<-1亿(出货)",
                           detail=detail)

    return FactorScore(score=s, detail=detail)
