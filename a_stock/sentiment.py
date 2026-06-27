"""情绪温度计: 北向资金 + 龙虎榜 + 研报热度 → 0-100 分."""
import argparse
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
import a_stock.config as cfg

STATE_FILE = cfg.DATA_DIR / "sentiment_state.json"


def _north_flow() -> tuple[float, str]:
    """北向资金: 推 iFind 或 eastmoney, 简化用 push2 试试."""
    import urllib.request
    # push2 北向资金接口
    url = "https://push2.eastmoney.com/api/qt/kamt/get?fields=f51,f52,f54,f60&klt=1&lmt=1&fields=f51,f52,f54,f60"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        d = data.get("data", {})
        if d:
            hk2sh = d.get("f60", 0) or 0  # 沪股通净流入
            hk2sz = d.get("f54", 0) or 0  # 深股通净流入
            return hk2sh + hk2sz, "live"
    except Exception:
        pass
    return 0, "fail"


def _dragon_tiger_count(trade_date: str) -> tuple[int, str]:
    """龙虎榜条数: 越活跃=情绪高, 简化从 screener DB 拉."""
    try:
        with sqlite3.connect(str(cfg.SCREENER_DB)) as c:
            row = c.execute("""
                SELECT COUNT(*) FROM sector_history
                WHERE scan_date=? AND sector_type='dragon_tiger'
            """, (trade_date,)).fetchone()
            return row[0] if row else 0, "ok"
    except Exception:
        return 0, "fail"


def _report_volume() -> tuple[int, str]:
    """近 7 日研报数: screener DB 的 candidate_history.report_count_7d 求和."""
    try:
        with sqlite3.connect(str(cfg.SCREENER_DB)) as c:
            today = date.today()
            week_ago = (today - timedelta(days=7)).isoformat()
            row = c.execute("""
                SELECT COALESCE(SUM(report_count_7d), 0) FROM candidate_history
                WHERE scan_date >= ?
            """, (week_ago,)).fetchone()
            return int(row[0]) if row else 0, "ok"
    except Exception:
        return 0, "fail"


def compute_temp() -> dict:
    """算 0-100 温度分.
    北向: +50亿=+30分, -50亿=-30分
    龙虎榜: >30条=+20分, <10条=-10分
    研报: >500=+20分, <100=-10分
    """
    nf, nf_status = _north_flow()
    dt_count, dt_status = _dragon_tiger_count(str(date.today()))
    rep_vol, rep_status = _report_volume()

    # 北向: 单位 元
    nf_yi = nf / 1e8
    nf_score = max(-30, min(30, nf_yi * 0.6))

    # 龙虎榜
    if dt_count > 30:
        dt_score = 20
    elif dt_count > 20:
        dt_score = 10
    elif dt_count > 10:
        dt_score = 0
    else:
        dt_score = -10

    # 研报
    if rep_vol > 500:
        rep_score = 20
    elif rep_vol > 200:
        rep_score = 10
    elif rep_vol > 100:
        rep_score = 0
    else:
        rep_score = -10

    base = 50
    total = base + nf_score + dt_score + rep_score
    total = max(0, min(100, total))

    if total >= 70:
        mood = "亢奋"
    elif total >= 55:
        mood = "乐观"
    elif total >= 45:
        mood = "中性"
    elif total >= 30:
        mood = "谨慎"
    else:
        mood = "恐慌"

    return {
        "date": str(date.today()),
        "ts": datetime.now().isoformat(),
        "temp": total,
        "mood": mood,
        "components": {
            "north_flow_yi": round(nf_yi, 2),
            "north_flow_score": round(nf_score, 1),
            "dragon_tiger_count": dt_count,
            "dragon_tiger_score": dt_score,
            "report_volume": rep_vol,
            "report_score": rep_score,
        },
        "status": {"north": nf_status, "dt": dt_status, "report": rep_status},
    }


def cycle_stage() -> dict:
    """6阶段情绪周期 (抄 quantdash fetch_sentiment_cycle_snapshots.py:558-634).
    退潮/冰点/修复/主升/试错/分歧. 用涨停池数据判断."""
    from a_stock.a_stock_data import limit_up_pool, broken_board_pool
    try:
        zt = limit_up_pool()
        zb = broken_board_pool()
    except Exception:
        return {"stage": "未知", "confidence": 0, "reason": "涨停池拉取失败"}

    total_zt = zt.get("total", 0)
    high_board = zt.get("high_board", 0)
    first_board = zt.get("first_board", 0)
    max_boards = max([zt.get("first_board", 0), zt.get("second_board", 0),
                      zt.get("third_board", 0), zt.get("high_board", 0)] + [0])
    broken_count = zb.get("total", 0)
    broken_rate = (broken_count / total_zt * 100) if total_zt > 0 else 0
    first_ratio = (first_board / total_zt * 100) if total_zt > 0 else 0

    # 高位风险 (抄 quantdash fetch_sentiment_cycle_snapshots.py:483-514)
    risk = "low"
    if broken_rate >= 35 or high_board >= 2:
        risk = "high"
    elif broken_rate >= 20 or high_board >= 1:
        risk = "medium"

    # 阶段判定 (first-match, 抄 quantdash)
    if risk == "high":
        stage = "退潮"
    elif max_boards <= 2 and total_zt < 20:
        stage = "冰点"
    elif broken_rate < 35 and total_zt > 0:
        stage = "修复"
    elif total_zt >= 5 and high_board >= 3 and max_boards >= 5:
        stage = "主升"
    elif first_ratio >= 60 or max_boards <= 4:
        stage = "试错"
    else:
        stage = "分歧"

    # confidence (简化)
    conf = {"主升": 72, "修复": 68, "退潮": 75, "冰点": 70, "试错": 62, "分歧": 62}.get(stage, 50)
    if risk == "low":
        conf += 6
    elif risk == "high":
        conf += 8
    conf = min(95, conf)

    return {
        "stage": stage,
        "confidence": conf,
        "risk_level": risk,
        "limit_up_total": total_zt,
        "high_board": high_board,
        "max_boards": max_boards,
        "broken_count": broken_count,
        "broken_rate": round(broken_rate, 1),
        "first_board_ratio": round(first_ratio, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = compute_temp()

    if STATE_FILE.exists():
        history = json.loads(STATE_FILE.read_text())
    else:
        history = []
    history.append({k: v for k, v in r.items() if k != "components"})
    history = history[-30:]
    STATE_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2))

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return

    print(f"=== 情绪温度 ({r['date']}) ===\n")
    print(f"  温度:    {r['temp']} / 100  ({r['mood']})")
    print()
    print(f"  北向资金:  {r['components']['north_flow_yi']:>+.2f} 亿  "
          f"({r['components']['north_flow_score']:+.0f} 分)  [{r['status']['north']}]")
    print(f"  龙虎榜:    {r['components']['dragon_tiger_count']:>3} 条  "
          f"({r['components']['dragon_tiger_score']:+.0f} 分)  [{r['status']['dt']}]")
    print(f"  研报数:    {r['components']['report_volume']:>4} 篇  "
          f"({r['components']['report_score']:+.0f} 分)  [{r['status']['report']}]")

    print("\n操作建议:")
    if r["temp"] >= 70:
        print("  ⚠️ 情绪亢奋, 考虑分批止盈")
    elif r["temp"] >= 55:
        print("  🟢 情绪乐观, 正常持有")
    elif r["temp"] >= 45:
        print("  🟡 情绪中性, 观望")
    elif r["temp"] >= 30:
        print("  🟠 情绪谨慎, 严格止损")
    else:
        print("  🔴 情绪恐慌, 可能是机会也可能是陷阱")


if __name__ == "__main__":
    main()
