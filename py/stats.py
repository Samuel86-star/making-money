"""复盘统计查询。"""
import argparse
import sys
from datetime import datetime, timedelta
import py.config as cfg
import py.db as db


def _query(sql: str, params: tuple = ()) -> list:
    with db.conn(cfg.DECISIONS_DB) as c:
        return c.execute(sql, params).fetchall()


def _closed_in_window(window_days: int | None) -> list:
    sql = "SELECT * FROM decisions WHERE close_date IS NOT NULL"
    params = []
    if window_days:
        from datetime import date
        cutoff = (date.today() - timedelta(days=window_days)).isoformat()
        sql += " AND close_date >= ?"
        params.append(cutoff)
    return _query(sql, tuple(params))


def compute_overall(window_days: int | None = None) -> dict:
    rows = _closed_in_window(window_days)
    if not rows:
        return {"total": 0, "win_rate": 0, "avg_pnl": 0, "discipline_rate": 0}
    wins = sum(1 for r in rows if (r["pnl_pct"] or 0) > 0)
    disciplined = sum(1 for r in rows if r["close_reason"] in ("target", "stop_loss"))
    return {
        "total": len(rows),
        "win_rate": round(wins / len(rows), 4),
        "avg_pnl": round(sum(r["pnl_pct"] or 0 for r in rows) / len(rows), 2),
        "discipline_rate": round(disciplined / len(rows), 4),
    }


def compute_by_strategy(strategy: str, window_days: int | None = None) -> dict:
    rows = [r for r in _closed_in_window(window_days) if r["strategy"] == strategy]
    return _agg(rows)


def _agg(rows) -> dict:
    if not rows:
        return {"total": 0, "win_rate": 0, "avg_pnl": 0}
    wins = sum(1 for r in rows if (r["pnl_pct"] or 0) > 0)
    return {
        "total": len(rows),
        "win_rate": round(wins / len(rows), 4),
        "avg_pnl": round(sum(r["pnl_pct"] or 0 for r in rows) / len(rows), 2),
    }


def compute_by_code(code: str) -> dict:
    rows = _query("SELECT * FROM decisions WHERE code=? AND close_date IS NOT NULL", (code,))
    return _agg(rows)


def compute_discipline(window_days: int = 90) -> dict:
    rows = _closed_in_window(window_days)
    if not rows:
        return {"tp_execution": 0, "sl_execution": 0, "early_exit": 0, "panic_exit": 0, "avg_hold_dev": 0}
    profit = [r for r in rows if (r["pnl_pct"] or 0) > 0]
    loss = [r for r in rows if (r["pnl_pct"] or 0) < 0]
    tp_exec = (sum(1 for r in profit if r["close_reason"] == "target") / len(profit)) if profit else 0
    sl_exec = (sum(1 for r in loss if r["close_reason"] == "stop_loss") / len(loss)) if loss else 0
    early = sum(1 for r in rows if r["close_reason"] == "manual" and (r["pnl_pct"] or 0) > 0)
    panic = sum(1 for r in rows if r["close_reason"] == "manual" and (r["pnl_pct"] or 0) < 0)
    devs = []
    for r in rows:
        if r["plan_hold_days"]:
            d1 = datetime.strptime(r["decision_date"], "%Y-%m-%d")
            d2 = datetime.strptime(r["close_date"], "%Y-%m-%d")
            devs.append((d2 - d1).days - r["plan_hold_days"])
    return {
        "tp_execution": round(tp_exec, 4),
        "sl_execution": round(sl_exec, 4),
        "early_exit": round(early / len(rows), 4),
        "panic_exit": round(panic / len(rows), 4),
        "avg_hold_dev": round(sum(devs) / len(devs), 2) if devs else 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=["short", "mid"])
    ap.add_argument("--code")
    ap.add_argument("--discipline", action="store_true")
    ap.add_argument("--window", type=int, default=90)
    ap.add_argument("--recent", type=int, default=20)
    ap.add_argument("--export")
    args = ap.parse_args()

    if args.discipline:
        s = compute_discipline(args.window)
        print("纪律性报告(window=%d 天):" % args.window)
        for k, v in s.items():
            print(f"  {k}: {v}")
    elif args.code:
        s = compute_by_code(args.code)
        print(f"按股 {args.code}: {s}")
    elif args.strategy:
        s = compute_by_strategy(args.strategy, args.window)
        print(f"按策略 {args.strategy}: {s}")
    else:
        s = compute_overall(args.window)
        print(f"总览(window={args.window}天): {s}")


if __name__ == "__main__":
    main()