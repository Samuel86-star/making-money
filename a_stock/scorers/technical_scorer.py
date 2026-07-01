"""技术面评分 (35%): MA/MACD/RSI 分档.
不抄 KHunter 读'策略命中表' (耦合过重), 直接算指标."""
from datetime import datetime, timedelta
from . import FactorScore
import a_stock.config as cfg


def _load_ohlcv(code: str, days: int = 120) -> list[dict]:
    """从 OHLCV 缓存加载日线 (parquet)."""
    f = cfg.OHLCV_DIR / f"{code}.parquet"
    if not f.exists():
        return []
    try:
        import pandas as pd
        df = pd.read_parquet(f)
        # 取最近 days 天, 按日期升序
        if "date" in df.columns:
            df = df.sort_values("date")
        df = df.tail(days)
        return df.to_dict("records")
    except Exception:
        return []


def _sma(values: list[float], n: int) -> float:
    if len(values) < n:
        return 0
    return sum(values[-n:]) / n


def _rsi(closes: list[float], n: int = 14) -> float:
    if len(closes) < n + 1:
        return 50
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    gains, losses = gains[-n:], losses[-n:]
    avg_gain = sum(gains) / n
    avg_loss = sum(losses) / n
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _macd(closes: list[float]):
    """返回 (dif, dea, hist)."""
    if len(closes) < 35:
        return 0, 0, 0
    ema12 = closes[0]
    ema26 = closes[0]
    difs = []
    for c in closes[1:]:
        ema12 = c * 2 / 13 + ema12 * 11 / 13
        ema26 = c * 2 / 27 + ema26 * 25 / 27
        difs.append(ema12 - ema26)
    dea = sum(difs[-9:]) / 9 if len(difs) >= 9 else 0
    dif = difs[-1]
    hist = 2 * (dif - dea)
    return dif, dea, hist


def _range_pct(seg: list[float]) -> float:
    """段内 (max-min)/min × 100. 用于VCP收缩幅度."""
    if not seg or min(seg) <= 0:
        return 0.0
    return (max(seg) - min(seg)) / min(seg) * 100


def _detect_vcp(closes: list[float], vols: list[float]) -> dict | None:
    """Minervini VCP (Volatility Contraction Pattern) 检测, A股适配.

    强化 [A] 强势入场假设. 2026-07-01 修正 (回测发现旧版无edge):
    必须含**突破确认** — 收缩形态 + 当日突破 right 段高 + 放量, 才触发.
    旧版只检收缩 → 假形态(收缩后继续震荡)误命中 → 三horizon edge全≈0.

    逻辑: base (排除当日) 需收缩 (左>中>右, 右≤0.6×左) + 趋势 + 强势;
    当日 (closes[-1]) 需 > right段高 (突破) + 当日量 ≥1.3×20日均 (放量).

    返回 dict(left_range, mid_range, right_range, contractions, breakout_high, vol_confirm) 或 None.
    """
    n = len(closes)
    if n < 60:
        return None
    price = closes[-1]          # 当日 = 候选突破日
    base = closes[:-1]          # base = 排除当日的收缩形态
    base_v = vols[:-1] if len(vols) >= n else vols
    ma20 = _sma(base, 20) if len(base) >= 20 else _sma(closes, 20)
    ma60 = _sma(base, 60) if len(base) >= 60 else _sma(closes, 60)
    if ma20 <= 0 or ma60 <= 0:
        return None
    # 趋势模板: 当日价 > MA20 > MA60 (今日强, base 在多头)
    if not (price > ma20 > ma60):
        return None
    # MA60 上行 (20日前 < 今日)
    if len(base) >= 80:
        ma60_past = _sma(base[:-20], 60)
        if ma60_past > 0 and ma60_past >= ma60:
            return None
    # 强势: 当日价距 base 近60日低 ≥15%
    lookback = min(len(base), 60)
    low60 = min(base[-lookback:])
    if low60 <= 0 or price < low60 * 1.15:
        return None
    # base 收缩: base 末40日分3段, 右<中<左 且 右≤0.6×左
    w = base[-min(len(base), 40):]
    seg = len(w) // 3
    if seg < 5:
        return None
    left_c, mid_c, right_c = w[-3 * seg:-2 * seg], w[-2 * seg:-seg], w[-seg:]
    lr, mr, rr = _range_pct(left_c), _range_pct(mid_c), _range_pct(right_c)
    if not (lr > mr > rr > 0 and rr <= 0.6 * lr):
        return None
    # ⭐ 突破确认: 当日价 > right 段高 (突破收缩上沿)
    right_high = max(right_c)
    if price <= right_high * 1.001:
        return None
    # 当日放量 (≥1.3× base 20日均)
    vol_confirm = False
    if len(vols) >= 1 and len(base_v) >= 20:
        avg_vol = sum(base_v[-20:]) / 20
        if avg_vol > 0:
            vol_confirm = vols[-1] >= avg_vol * 1.3
    contractions = 2 if (lr > mr > rr) else 1
    return {"left_range": round(lr, 3), "mid_range": round(mr, 3),
            "right_range": round(rr, 3), "contractions": contractions,
            "breakout_high": round(right_high, 2),
            "vol_confirm": vol_confirm}


def _detect_wyckoff(closes: list[float], vols: list[float]) -> dict | None:
    """Wyckoff 派发/吸筹识别 (简化版, 喂 [J] 出货假设).

    用 close (HIGH/LOW 部分缓存缺失, 与 _detect_vcp 同口径).
    - 区间窗: 截至约5日前的25日 (排除最近动作, 纯粹既有区间).
    - 突破尝试窗: 近5日 (排除当日).
    - UTAD (派发): 近5日峰值放量破区间上沿, 但当日跌回区间内 = 假突破, 出货.
    - Spring (吸筹): 近5日谷值放量破区间下沿, 但当日升回区间内 = 假跌破, 收集.
    - 量能不对称: 区间内下跌放量/上涨缩量=隐性派发, 反之=隐性吸筹.

    返回 dict(phase, signal, ...) 或 None.
    """
    n = len(closes)
    if n < 30 or len(vols) < 30:
        return None
    price = closes[-1]
    range_c = closes[-30:-5]    # 既有区间 (排除近5日动作)
    range_v = vols[-30:-5]
    range_high = max(range_c)
    range_low = min(range_c)
    rng = range_high - range_low
    if rng <= 0:
        return None
    avg_vol = sum(range_v) / len(range_v)
    recent_c = closes[-6:-1]     # 近5日突破尝试 (排除当日)
    recent_v = vols[-6:-1]
    peak = max(recent_c)
    trough = min(recent_c)
    peak_vol = recent_v[recent_c.index(peak)]
    trough_vol = recent_v[recent_c.index(trough)]
    # UTAD: 峰值真破区间上沿 + 放量1.8× + 当日跌回区间内
    utad = (peak > range_high
            and peak_vol >= avg_vol * 1.8
            and price <= range_high)
    # Spring: 谷值真破区间下沿 + 放量1.8× + 当日升回区间内
    spring = (trough < range_low
              and trough_vol >= avg_vol * 1.8
              and price >= range_low)
    # 量能不对称辅证 (近20日含当日, 上涨日 vs 下跌日总量)
    seg = closes[-20:]
    seg_v = vols[-20:]
    up_vol = down_vol = 0.0
    for i in range(1, len(seg)):
        if seg[i] > seg[i - 1]:
            up_vol += seg_v[i]
        elif seg[i] < seg[i - 1]:
            down_vol += seg_v[i]
    ratio = down_vol / up_vol if up_vol > 0 else 1.0
    vol_bias = "down_heavy" if ratio >= 1.5 else ("up_heavy" if ratio <= 0.67 else "balanced")
    in_range = range_low <= price <= range_high

    if utad:
        return {"phase": "distribution", "signal": "UTAD",
                "peak": round(peak, 2), "range_high": round(range_high, 2),
                "pullback_pct": round((peak - price) / peak * 100, 1),
                "vol_bias": vol_bias, "vol_ratio": round(ratio, 2)}
    if spring:
        return {"phase": "accumulation", "signal": "Spring",
                "trough": round(trough, 2), "range_low": round(range_low, 2),
                "recovery_pct": round((price - trough) / trough * 100, 1),
                "vol_bias": vol_bias, "vol_ratio": round(ratio, 2)}
    if vol_bias == "down_heavy" and in_range:
        return {"phase": "distribution", "signal": "vol_asymmetry",
                "vol_ratio": round(ratio, 2), "note": "下跌放量上涨缩量, 转弱手"}
    if vol_bias == "up_heavy" and in_range:
        return {"phase": "accumulation", "signal": "vol_asymmetry",
                "vol_ratio": round(ratio, 2), "note": "上涨放量下跌缩量, 转强手"}
    return None


def score(code: str) -> FactorScore:
    """技术面分档评分. base 50, 加减分."""
    rows = _load_ohlcv(code)
    if len(rows) < 35:
        return FactorScore(score=50, detail={"reason": "数据不足"})

    # 适配列名 (Open/High/Low/Close/Volume 首字母大写)
    closes = [r.get("Close") or r.get("close") for r in rows if r.get("Close") or r.get("close")]
    vols = [r.get("Volume") or r.get("volume") for r in rows
            if r.get("Volume") or r.get("volume")]
    ma5 = _sma(closes, 5)
    ma10 = _sma(closes, 10)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)
    rsi = _rsi(closes)
    dif, dea, hist = _macd(closes)
    price = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else price
    price_up = price > prev_close

    s = 50
    detail = {"ma5": round(ma5, 2), "ma10": round(ma10, 2), "ma20": round(ma20, 2), "rsi": round(rsi, 1)}

    # 均线多头 (价>ma5>ma20>ma60)
    if price > ma5 > ma20 > ma60 and ma60 > 0:
        s += 25
        detail["ma_alignment"] = "多头排列"
    elif price > ma20:
        s += 10
        detail["ma_alignment"] = "价上ma20"
    elif price < ma20 < ma5:
        s -= 20
        detail["ma_alignment"] = "空头排列"

    # MACD 金叉 (hist>0 且 dif>dea)
    if hist > 0 and dif > dea:
        s += 15
        detail["macd"] = "金叉"
    elif hist < 0 and dif < dea:
        s -= 15
        detail["macd"] = "死叉"

    # RSI
    if rsi < 30:
        s += 10  # 超卖反弹机会
        detail["rsi_state"] = "超卖"
    elif rsi > 70:
        s -= 10  # 超买
        detail["rsi_state"] = "超买"

    # 回踩买点 (06-29铁律: 多头排列+回踩MA5/MA10不破=加仓信号)
    if ma60 > 0 and price > ma20 > ma60:  # 多头基础
        for ma_name, ma_val in [("MA5", ma5), ("MA10", ma10)]:
            if ma_val <= 0:
                continue
            # 回踩: 价在MA±1.5%内, 且价>=MA(不破)
            if ma_val * 0.998 <= price <= ma_val * 1.015:
                detail["pullback_buy"] = f"回踩{ma_name}"
                s += 8
                break

    # 量价验证 (volume 历史未用, 06-29教训核心补强)
    # 量比 = 当日量 / 近20日均量
    vol_ratio = 1.0
    if len(vols) >= 20:
        avg_vol = sum(vols[-21:-1]) / 20 if len(vols) >= 21 else sum(vols[-20:]) / 20
        if avg_vol > 0:
            vol_ratio = vols[-1] / avg_vol
    high20 = max(closes[-20:]) if len(closes) >= 20 else price
    if vol_ratio != 1.0:
        if price_up and price > high20 * 0.999 and vol_ratio >= 1.5:
            s += 10
            detail["vol_breakout"] = "放量突破"
        elif price_up and vol_ratio < 0.7:
            s -= 8
            detail["vol_divergence"] = "价升量缩"
        elif not price_up and vol_ratio >= 1.5:
            s -= 10
            detail["vol_breakdown"] = "放量破位"
        elif not price_up and vol_ratio < 0.8:
            s += 5  # 缩量破位=洗盘, 反向加分
            detail["vol_breakdown"] = "缩量洗盘"

    # VCP 强势入场 setup (Minervini SEPA, 强化 [A] 假设, 2026-07-01 加突破确认)
    vcp = _detect_vcp(closes, vols)
    if vcp:
        if vcp["vol_confirm"]:
            s += 12
            detail["vcp_setup"] = f"VCP突破({vcp['contractions']}收缩+放量, 末{vcp['right_range']:.1f}%)"
        else:
            s += 6
            detail["vcp_setup"] = f"VCP突破({vcp['contractions']}收缩, 量未放)"

    # Wyckoff 派发/吸筹 (强化 [J] 出货假设: 派发-10/吸筹+8)
    wyck = _detect_wyckoff(closes, vols)
    if wyck:
        if wyck["phase"] == "distribution":
            s -= 10
            detail["wyckoff"] = f"派发({wyck['signal']})"
        else:
            s += 8
            detail["wyckoff"] = f"吸筹({wyck['signal']})"

    return FactorScore(score=s, detail=detail)
