"""市场结构识别: Distribution Day (派发日) + FTD (Follow-Through Day).

借鉴 O'Neil/IBD 派 (docs/references/trading-skills-methodology.md 第4条).
A股化: 套到指数ETF (159915创业板/510300沪深300) 上判市场风险等级.
比 sentiment 温度硬 — 结构信号 > 模糊温度."""
import argparse
from datetime import date
from a_stock.ohlcv import load_ohlcv
import a_stock.ohlcv as ohlcv

# 派发日参数
DIST_DROP_MIN = 0.002   # 收盘跌 ≥0.2%
FTD_GAIN_MIN = 0.015    # FTD 放量涨 ≥1.5%
FTD_WINDOW = (4, 7)     # FTD 出现在跌势启动后第4-7天
FTD_VOL_RATIO = 1.2     # FTD 量 ≥ 前日均量 ×1.2

# 风险等级阈值 (派发日计数, 近25日)
LEVELS = [
    (0, "NORMAL"),
    (2, "CAUTION"),
    (4, "HIGH"),
    (6, "SEVERE"),
]


def regime_from_count(count: int) -> str:
    """派发日计数 → 风险等级."""
    level = "NORMAL"
    for threshold, name in LEVELS:
        if count >= threshold:
            level = name
    return level


def _index_df(code: str):
    """加载指数ETF OHLCV, 容错."""
    try:
        df = load_ohlcv(code)
    except FileNotFoundError:
        return None
    return df


def distribution_days(code: str, lookback: int = 25) -> dict:
    """派发日: 收盘跌≥0.2% 且 量>前日量. 返回 {count, days:[{date,pct,vol_ratio}]}.

    O'Neil派发日规则: 主要指数收盘下跌 (≥0.2%) 且成交量放大 = 机构抛售.
    累积4-5个 = 市场见顶信号."""
    df = _index_df(code)
    if df is None or len(df) < 3:
        return {"count": 0, "days": []}
    df = df.tail(lookback).reset_index(drop=True)
    closes = df["close"].astype(float).tolist()
    vols = df["volume"].astype(float).tolist()
    dates = df["date"].astype(str).tolist() if "date" in df.columns else [str(i) for i in range(len(df))]
    days = []
    for i in range(1, len(closes)):
        prev_c, cur_c = closes[i - 1], closes[i]
        if prev_c <= 0:
            continue
        pct = (cur_c - prev_c) / prev_c
        vol_ratio = vols[i] / vols[i - 1] if vols[i - 1] > 0 else 1.0
        if pct <= -DIST_DROP_MIN and vol_ratio > 1.0:
            days.append({"date": dates[i], "pct": round(pct * 100, 2),
                         "vol_ratio": round(vol_ratio, 2)})
    return {"count": len(days), "days": days[-10:]}


def ftd_signal(code: str, lookback: int = 30) -> dict | None:
    """Follow-Through Day: 跌势后第4-7天放量涨≥1.5% = 反弹确认.

    O'Neil FTD: 市场见底后, 第4-7个交易日出现放量上涨 (≥1.5%) = 机构进场确认.
    返回最近FTD {date, pct, vol_ratio} 或 None."""
    df = _index_df(code)
    if df is None or len(df) < 5:
        return None
    df = df.tail(lookback).reset_index(drop=True)
    closes = df["close"].astype(float).tolist()
    vols = df["volume"].astype(float).tolist()
    dates = df["date"].astype(str).tolist() if "date" in df.columns else [str(i) for i in range(len(df))]

    # 找跌势启动点: 连续2日跌
    downtrend_start = None
    for i in range(2, len(closes)):
        if closes[i] < closes[i - 1] < closes[i - 2]:
            downtrend_start = i - 2
            break
    if downtrend_start is None:
        return None

    # 在跌势后 FTD_WINDOW(4-7) 天内找放量涨
    for offset in range(FTD_WINDOW[0], FTD_WINDOW[1] + 1):
        idx = downtrend_start + offset
        if idx < 1 or idx >= len(closes):
            continue
        prev_c = closes[idx - 1]
        if prev_c <= 0:
            continue
        pct = (closes[idx] - prev_c) / prev_c
        avg_vol_prev = sum(vols[max(0, idx - 5):idx]) / max(1, idx - max(0, idx - 5))
        vol_ratio = vols[idx] / avg_vol_prev if avg_vol_prev > 0 else 0
        if pct >= FTD_GAIN_MIN and vol_ratio >= FTD_VOL_RATIO:
            return {"date": dates[idx], "pct": round(pct * 100, 2),
                    "vol_ratio": round(vol_ratio, 2), "offset": offset}
    return None


def regime(code: str = "159915") -> dict:
    """市场风险等级综合: 派发日 + FTD. 返回 {level, dist_count, ftd}."""
    dd = distribution_days(code)
    level = regime_from_count(dd["count"])
    ftd = ftd_signal(code)
    return {"code": code, "level": level, "dist_count": dd["count"],
            "dist_days": dd["days"], "ftd": ftd}


def main():
    ap = argparse.ArgumentParser(description="市场结构识别 (派发日+FTD)")
    ap.add_argument("--code", default="159915", help="指数ETF代码 (默认159915创业板)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = regime(args.code)
    print(f"=== 市场结构 ({args.code}) {date.today()} ===")
    print(f"风险等级: {r['level']}")
    print(f"近25日派发日: {r['dist_count']} 个")
    if r["dist_days"]:
        print("  派发日明细:")
        for d in r["dist_days"][-5:]:
            print(f"    {d['date']}  跌{d['pct']}%  量比{d['vol_ratio']}")
    if r["ftd"]:
        print(f"FTD信号: {r['ftd']['date']} 涨{r['ftd']['pct']}% 量比{r['ftd']['vol_ratio']} (跌势后第{r['ftd']['offset']}日)")
    else:
        print("FTD信号: 无 (无近期见底确认)")
    print()
    print("等级含义: NORMAL(可进攻) / CAUTION(减仓) / HIGH(防御) / SEVERE(清仓)")
    if args.json:
        import json
        print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
