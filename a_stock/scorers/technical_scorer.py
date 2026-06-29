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
            if abs(price - ma_val) / ma_val <= 0.015 and price >= ma_val * 0.998:
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

    return FactorScore(score=s, detail=detail)
