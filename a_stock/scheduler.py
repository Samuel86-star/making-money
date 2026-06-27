"""调度器: 多时间点 + 持久化 + 6段交易时段 + 节假日.
抄 aiagents-stock portfolio_scheduler.py:551-554 多时间点思路, 补:
- 持久化 (aiagents-stock 重启丢失, 我存DB)
- WAL (aiagents-stock 无WAL有locked风险)
- 节假日 (aiagents-stock 未实现, 用内置判断)
- 6段交易时段 (抄 aiagents-stock smart_monitor_deepseek.py:61-140)"""
import argparse
import json
import sqlite3
from datetime import datetime, date, time as dtime
from pathlib import Path
import a_stock.config as cfg

SCHED_DB = cfg.DATA_DIR / "scheduler.sqlite"

# 默认调度时间表
DEFAULT_SCHEDULE = {
    "morning_scan_1": "09:35",   # 早盘速览
    "morning_scan_2": "09:50",   # 早盘确认
    "close_scan": "15:10",       # 盘后落盘
}


def _init_db() -> None:
    with sqlite3.connect(str(SCHED_DB)) as c:
        c.execute("PRAGMA journal_mode=WAL")  # 补 WAL (修 aiagents-stock locked风险)
        c.execute("""
            CREATE TABLE IF NOT EXISTS schedule (
                key TEXT PRIMARY KEY,
                time TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                last_run TEXT
            )
        """)
        for k, t in DEFAULT_SCHEDULE.items():
            c.execute("INSERT OR IGNORE INTO schedule (key, time, enabled) VALUES (?,?,1)",
                      (k, t))


# 6段交易时段 (抄 aiagents-stock smart_monitor_deepseek.py:82-140)
def trading_session(now: datetime | None = None) -> dict:
    """返回 {session, can_trade}. 6段: 休市/集合竞价/上午盘/午休/下午盘/尾盘/盘后.
    考虑调休上班周末 (MAKE_WORK_2026)."""
    now = now or datetime.now()
    if now.weekday() >= 5 and now.date() not in MAKE_WORK_2026:
        return {"session": "休市", "can_trade": False}
    if is_holiday(now.date()):
        return {"session": "休市", "can_trade": False}
    t = now.time()
    if dtime(9, 0) <= t < dtime(9, 30):
        return {"session": "集合竞价", "can_trade": False}
    if dtime(9, 30) <= t <= dtime(11, 30):
        return {"session": "上午盘", "can_trade": True}
    if dtime(11, 30) < t < dtime(13, 0):
        return {"session": "午间休市", "can_trade": False}
    if dtime(13, 0) <= t <= dtime(15, 0):
        if t >= dtime(14, 30):
            return {"session": "尾盘", "can_trade": True}
        return {"session": "下午盘", "can_trade": True}
    return {"session": "盘后", "can_trade": False}


# 节假日判断 (补 aiagents-stock 未实现的部分)
# 2026年数据来自国务院办公厅国办发明电〔2025〕7号
HOLIDAYS_2026 = {
    # 元旦 (1/1 周四 - 1/3 周六, 1/4 周日补班)
    date(2026, 1, 1), date(2026, 1, 2),
    # 春节 (2/15 周日 - 2/23 周一)
    date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),
    date(2026, 2, 19), date(2026, 2, 20), date(2026, 2, 23),
    # 清明 (4/4 周六 - 4/6 周一)
    date(2026, 4, 6),
    # 劳动节 (5/1 周五 - 5/5 周二)
    date(2026, 5, 1), date(2026, 5, 4), date(2026, 5, 5),
    # 端午 (6/19 周五 - 6/21 周日)
    date(2026, 6, 19),
    # 中秋 (9/25 周五 - 9/27 周日)
    date(2026, 9, 25),
    # 国庆 (10/1 周四 - 10/7 周三)
    date(2026, 10, 1), date(2026, 10, 2),
    date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7),
}

# 调休上班: 周末变工作日 (市场开市)
MAKE_WORK_2026 = {
    date(2026, 1, 4),    # 元旦调休 (周日)
    date(2026, 2, 14),   # 春节调休 (周六)
    date(2026, 2, 28),   # 春节调休 (周六)
    date(2026, 5, 9),    # 劳动节调休 (周六)
    date(2026, 9, 20),   # 国庆调休 (周日)
    date(2026, 10, 10),  # 国庆调休 (周六)
}


def is_holiday(d: date) -> bool:
    """节假日判断. 调休上班周末不算假日."""
    if d in MAKE_WORK_2026:
        return False
    return d in HOLIDAYS_2026


def get_schedule() -> list[dict]:
    """读持久化调度表."""
    _init_db()
    with sqlite3.connect(str(SCHED_DB)) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT * FROM schedule ORDER BY time").fetchall()
    return [dict(r) for r in rows]


def set_time(key: str, time_str: str) -> None:
    """改调度时间 (热重载, 持久化)."""
    _init_db()
    with sqlite3.connect(str(SCHED_DB)) as c:
        c.execute("INSERT OR REPLACE INTO schedule (key, time, enabled) VALUES (?,?,1)",
                  (key, time_str))


def toggle(key: str, enabled: bool) -> None:
    _init_db()
    with sqlite3.connect(str(SCHED_DB)) as c:
        c.execute("UPDATE schedule SET enabled=? WHERE key=?",
                  (1 if enabled else 0, key))


def mark_run(key: str) -> None:
    """标记某任务已跑 (防当日重复)."""
    _init_db()
    with sqlite3.connect(str(SCHED_DB)) as c:
        c.execute("UPDATE schedule SET last_run=? WHERE key=?",
                  (datetime.now().isoformat(), key))


def due_jobs() -> list[str]:
    """返回当前时刻该跑的任务 key (匹配 HH:MM 且当日未跑)."""
    now = datetime.now()
    # 非交易时段: 仅允许 15:00-15:30 盘后落盘 (close_scan)
    if not trading_session(now)["can_trade"]:
        if not (dtime(15, 0) <= now.time() <= dtime(15, 30)):
            return []
    now_hm = now.strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")
    jobs = []
    for s in get_schedule():
        if not s["enabled"]:
            continue
        if s["time"] != now_hm:
            continue
        last = s.get("last_run", "")
        if last and last.startswith(today):
            continue  # 今日已跑
        jobs.append(s["key"])
    return jobs


def run_due(dry_run: bool = False) -> dict:
    """跑当前到点的任务."""
    jobs = due_jobs()
    results = {}
    for key in jobs:
        try:
            if key.startswith("morning_scan"):
                from a_stock.morning_scan import scan
                r = scan(dry_run=dry_run)
                results[key] = r
            elif key == "close_scan":
                from a_stock.close_scan import run as close_run
                r = close_run(dry_run=dry_run)
                results[key] = r
            if not dry_run:
                mark_run(key)
        except Exception as e:
            results[key] = {"error": str(e)}
    return {"ran": jobs, "results": results}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")
    p_set = sub.add_parser("set")
    p_set.add_argument("key")
    p_set.add_argument("time")

    p_session = sub.add_parser("session")

    sub.add_parser("due")
    p_run = sub.add_parser("run")
    p_run.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()

    if args.cmd == "list":
        for s in get_schedule():
            en = "✓" if s["enabled"] else "✗"
            print(f"  {en} {s['key']:<18} {s['time']}  last={s.get('last_run') or '-'}")
    elif args.cmd == "set":
        set_time(args.key, args.time)
        print(f"✓ {args.key} → {args.time}")
    elif args.cmd == "session":
        s = trading_session()
        print(f"当前: {s['session']} (can_trade={s['can_trade']})")
    elif args.cmd == "due":
        print("到点任务:", due_jobs() or "无")
    elif args.cmd == "run":
        r = run_due(args.dry_run)
        print(f"跑 {len(r['ran'])} 个: {r['ran']}")
        for k, v in r["results"].items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
