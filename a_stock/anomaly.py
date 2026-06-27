"""异动信号: 火箭发射 / 高台跳水.
抄 kimi_stock_advisor/database.py:122-215 的涨速+量比算法, 修午休 bug.

数据源: qt.gtimg.cn 实时价 + 本地 tick 缓存 (data/anomaly_ticks.sqlite)
触发:
  🚀 火箭发射: 3分钟涨速 > 1.0% 且 量比 > 1.5
  🌊 高台跳水: 3分钟涨速 < -1.0%"""
import argparse
import json
import re
import sqlite3
import time
import urllib.request
from datetime import datetime, date, time as dtime, timedelta
from pathlib import Path
import a_stock.config as cfg

TICK_DB = cfg.DATA_DIR / "anomaly_ticks.sqlite"

# 阈值 (抄 kimi config.py, 以代码为准非readme的-1.5%)
RISE_SPEED_THRESHOLD = 1.0    # 3分钟涨速 %
DROP_SPEED_THRESHOLD = -1.0
VOL_RATIO_THRESHOLD = 1.5

TRADING_SESSIONS = [
    (dtime(9, 25), dtime(11, 30)),
    (dtime(13, 0), dtime(15, 0)),
]


def _is_trading_time(now: datetime | None = None) -> bool:
    """交易时段判断 (含集合竞价, 排除午休). 修复 kimi 跨午休 bug.
    考虑调休上班周末 (scheduler.MAKE_WORK_2026)."""
    now = now or datetime.now()
    if now.weekday() >= 5:
        from a_stock.scheduler import MAKE_WORK_2026
        if now.date() not in MAKE_WORK_2026:
            return False
    t = now.time()
    for start, end in TRADING_SESSIONS:
        if start <= t <= end:
            return True
    return False


def _init_db() -> None:
    with sqlite3.connect(str(TICK_DB)) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                code TEXT NOT NULL,
                price REAL NOT NULL,
                volume REAL NOT NULL,
                change_pct REAL
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_code_ts ON ticks (code, timestamp DESC)
        """)


def _save_tick(code: str, price: float, volume: float, change_pct: float) -> None:
    _init_db()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(str(TICK_DB)) as c:
        c.execute(
            "INSERT INTO ticks (timestamp, code, price, volume, change_pct) VALUES (?,?,?,?,?)",
            (ts, code, price, volume, change_pct),
        )


def _load_recent_ticks(code: str, minutes: int = 30) -> list[dict]:
    """加载最近N分钟tick, 过滤午休 (修 kimi bug)."""
    _init_db()
    cutoff = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(str(TICK_DB)) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT timestamp, price, volume FROM ticks WHERE code=? AND timestamp>=? "
            "ORDER BY timestamp ASC",
            (code, cutoff),
        ).fetchall()

    out = []
    for r in rows:
        ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
        # 过滤午休时段的tick (虽然不应该有, 防御性)
        if not _is_trading_time(ts):
            continue
        out.append({"timestamp": ts, "price": r["price"], "volume": r["volume"]})
    return out


def _live_quote(code: str) -> dict | None:
    """qt.gtimg.cn 实时报价."""
    prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
    url = f"http://qt.gtimg.cn/q={prefix}{code}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = r.read().decode("gbk", errors="ignore")
        m = re.search(r'~' + code + r'~([0-9.]+)~[0-9.]+~[0-9]+~([0-9]+)~', data)
        if not m:
            return None
        price = float(m.group(1))
        volume = int(m.group(2))
        return {"price": price, "volume": volume}
    except Exception:
        return None


def calc_stats(code: str) -> dict:
    """算 3分钟涨速 + 量比. 抄 kimi database.py:156-197, 修午休."""
    ticks = _load_recent_ticks(code, minutes=30)
    if len(ticks) < 5:
        return {"speed_3min": 0.0, "vol_ratio": 1.0, "trend_desc": "数据不足", "n_ticks": len(ticks)}

    # 1. 3分钟涨速 (searchsorted 二分定位)
    now_time = ticks[-1]["timestamp"]
    target_time = now_time - timedelta(minutes=3)
    timestamps = [t["timestamp"] for t in ticks]
    # 手动二分 (datetime 列表无 searchsorted, 用 bisect)
    import bisect
    idx = bisect.bisect_left(timestamps, target_time)
    if idx >= len(ticks):
        idx = len(ticks) - 1
    if idx < 0:
        idx = 0

    price_now = ticks[-1]["price"]
    price_3min = ticks[idx]["price"]
    speed_3min = ((price_now - price_3min) / price_3min * 100) if price_3min > 0 else 0.0

    # 2. 量比 (累计量 → resample 1min → diff)
    import pandas as pd
    df = pd.DataFrame(ticks)
    df = df.set_index("timestamp").resample("1min").last().dropna(subset=["price"])
    df["vol_delta"] = df["volume"].diff()
    valid = df["vol_delta"].dropna()
    vol_ratio = 1.0
    if len(valid) >= 2:
        latest_vol = valid.iloc[-1]
        avg_vol = valid.iloc[:-1].tail(30).mean()
        if avg_vol and avg_vol > 0:
            vol_ratio = latest_vol / avg_vol

    # 3. 趋势描述
    if speed_3min > 1.0:
        trend = "快速上行"
    elif speed_3min < -1.0:
        trend = "快速下行"
    elif 0.5 < speed_3min <= 1.0:
        trend = "稳步推升"
    elif -1.0 <= speed_3min < -0.5:
        trend = "阴跌"
    else:
        trend = "震荡"

    return {
        "speed_3min": round(speed_3min, 2),
        "vol_ratio": round(vol_ratio, 2),
        "trend_desc": trend,
        "n_ticks": len(ticks),
    }


def check(code: str, name: str = "") -> dict | None:
    """检测异动. 返回信号 dict 或 None."""
    if not _is_trading_time():
        return None

    quote = _live_quote(code)
    if not quote:
        return None

    _save_tick(code, quote["price"], quote["volume"], 0)
    stats = calc_stats(code)

    speed = stats["speed_3min"]
    vol_ratio = stats["vol_ratio"]

    if speed > RISE_SPEED_THRESHOLD and vol_ratio > VOL_RATIO_THRESHOLD:
        return {
            "type": "🚀 火箭发射",
            "code": code, "name": name or code,
            "price": quote["price"],
            "speed_3min": speed, "vol_ratio": vol_ratio,
            "trend": stats["trend_desc"],
        }
    if speed < DROP_SPEED_THRESHOLD:
        return {
            "type": "🌊 高台跳水",
            "code": code, "name": name or code,
            "price": quote["price"],
            "speed_3min": speed, "vol_ratio": vol_ratio,
            "trend": stats["trend_desc"],
        }
    return None


def scan_holdings() -> list[dict]:
    """扫描所有持仓 + watchlist 异动."""
    from a_stock.anomaly_holdings_loader import load_targets  # 简化, 见下
    targets = load_targets()
    signals = []
    for t in targets:
        sig = check(t["code"], t.get("name", ""))
        if sig:
            signals.append(sig)
    return signals


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check")
    p_check.add_argument("code")
    p_check.add_argument("--name", default="")

    sub.add_parser("scan")

    p_stats = sub.add_parser("stats")
    p_stats.add_argument("code")

    args = ap.parse_args()

    if args.cmd == "check":
        sig = check(args.code, args.name)
        if sig:
            print(json.dumps(sig, ensure_ascii=False, indent=2))
        else:
            print(f"{args.code}: 无异动")
    elif args.cmd == "scan":
        sigs = scan_holdings()
        if sigs:
            print(f"=== 检测到 {len(sigs)} 个异动 ===")
            for s in sigs:
                print(f"  {s['type']} {s['name']}({s['code']}) "
                      f"价格{s['price']} 涨速{s['speed_3min']}% 量比{s['vol_ratio']}")
        else:
            print("无异动")
    elif args.cmd == "stats":
        s = calc_stats(args.code)
        print(json.dumps(s, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
