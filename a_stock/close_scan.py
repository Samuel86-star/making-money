"""盘后扫描: 15:10 落盘全天数据.
资金流final + 板块轮动snapshot + 情绪 + 候选评分 → 写DB (周日复盘用).
不用 Parquet/DuckDB (我数据量小, SQLite 够)."""
import argparse
import json
import sqlite3
from datetime import datetime, date
import a_stock.config as cfg
from a_stock.notifier import push


def _init_db() -> None:
    with sqlite3.connect(str(cfg.SCREENER_DB)) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_close (
                date TEXT PRIMARY KEY,
                close_at TEXT NOT NULL,
                sector_rotation TEXT,
                sentiment TEXT,
                candidates TEXT,
                status TEXT DEFAULT 'ok'
            )
        """)


def run(dry_run: bool = False) -> dict:
    """盘后落盘."""
    _init_db()
    today = date.today().isoformat()
    result = {"date": today, "close_at": datetime.now().isoformat()}

    # 1. 板块轮动 snapshot
    sector_data = None
    try:
        from a_stock.sector_rotation import snapshot_today, analyze
        snapshot_today()
        sr = analyze()
        if sr:
            sector_data = {
                "verdict": sr.verdict,
                "current_leader": sr.current_leader,
                "strongest_repeat": sr.strongest_repeat_name,
                "streak_days": sr.current_streak_days,
            }
            result["sector"] = sector_data
    except Exception as e:
        result["sector_error"] = str(e)

    # 2. 情绪温度
    sentiment_data = None
    try:
        from a_stock.sentiment import compute_temp
        sentiment_data = compute_temp()
        result["sentiment"] = {
            "temp": sentiment_data["temp"],
            "mood": sentiment_data["mood"],
        }
    except Exception as e:
        result["sentiment_error"] = str(e)

    # 3. 持仓评分快照
    candidates = []
    try:
        from a_stock.scorers.total_scorer import score_candidate, to_dict
        from a_stock.anomaly_holdings_loader import load_targets
        for t in load_targets()[:10]:  # top10
            ts = score_candidate(t["code"], t.get("name", ""))
            d = to_dict(ts)
            candidates.append({"code": d["code"], "name": d["name"],
                               "total": d["total"], "level": d["level"]})
        result["candidates"] = candidates
    except Exception as e:
        result["candidates_error"] = str(e)

    # 4. 落盘
    if not dry_run:
        with sqlite3.connect(str(cfg.SCREENER_DB)) as c:
            c.execute("""
                INSERT OR REPLACE INTO daily_close
                (date, close_at, sector_rotation, sentiment, candidates, status)
                VALUES (?,?,?,?,?,?)
            """, (today, result["close_at"],
                  json.dumps(sector_data, ensure_ascii=False),
                  json.dumps(result.get("sentiment"), ensure_ascii=False),
                  json.dumps(candidates, ensure_ascii=False, default=str),
                  "ok"))
        # 推送盘后摘要
        body_parts = []
        if sector_data:
            body_parts.append(f"板块:{sector_data['verdict']}")
        if result.get("sentiment"):
            body_parts.append(f"情绪:{result['sentiment']['temp']}({result['sentiment']['mood']})")
        if candidates:
            top = sorted(candidates, key=lambda x: x["total"], reverse=True)[:3]
            body_parts.append("top3: " + " ".join(f"{c['name']}{c['total']}" for c in top))
        push("📊 盘后摘要", " | ".join(body_parts), subtitle=today)

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    r = run(args.dry_run)
    print(f"\n=== 盘后落盘 {r['date']} ===")
    if r.get("sector"):
        print(f"板块: {r['sector']['verdict']} 领涨{r['sector']['current_leader']}")
    if r.get("sentiment"):
        print(f"情绪: {r['sentiment']['temp']} ({r['sentiment']['mood']})")
    if r.get("candidates"):
        print(f"持仓评分 top:")
        for c in sorted(r["candidates"], key=lambda x: x["total"], reverse=True)[:5]:
            print(f"  {c['name']} {c['total']} {c['level']}")


if __name__ == "__main__":
    main()
