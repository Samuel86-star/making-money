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
                industry_flow TEXT,
                status TEXT DEFAULT 'ok'
            )
        """)
        # 迁移: 旧库无 industry_flow 列则补 (幂等)
        cols = {row[1] for row in c.execute("PRAGMA table_info(daily_close)").fetchall()}
        if "industry_flow" not in cols:
            c.execute("ALTER TABLE daily_close ADD COLUMN industry_flow TEXT")


def _fetch_industry_flow(fetch_fn, retries: int = 2) -> tuple[dict | None, str | None]:
    """拉行业资金流带重试. 返回 (flow, err).

    15:10 盘后落盘时 industry_fund_flow 瞬时拉取失败常见 (网络/东财push2抖动),
    旧逻辑单次失败静默写 NULL → daily_close.industry_flow 历史缺口 (06-29/30/07-01全空).
    现加重试 + 调用方据此推送 warning, 不再静默.
    异常和空返回都视为失败 (防御: fetch_fn 返回 None 不抛异常时也不静默).
    """
    err = None
    for attempt in range(retries):
        try:
            flow = fetch_fn()
            if flow:
                return flow, None
            err = "返回空结果"
        except Exception as e:
            err = str(e)
        if attempt < retries - 1:
            print(f"  ⚠ 行业资金流拉取失败 (第 {attempt + 1} 次失败, 重试中): {err}")
    return None, err


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

    # 2b. 市场结构 (派发日+FTD, docs/references 第4条) — 比情绪温度硬
    regime_data = None
    try:
        from a_stock.market_regime import regime
        reg = regime("159915")
        regime_data = {"level": reg["level"], "dist_count": reg["dist_count"],
                       "ftd": reg["ftd"]}
        result["regime"] = regime_data
    except Exception as e:
        result["regime_error"] = str(e)

    # 2c. 行业资金流 (07-01实战新增: 每日必看, 避免被"涨却流出"骗)
    # 重试1次 (15:10 瞬时拉取失败常见, 旧逻辑静默写 NULL → 历史缺口)
    from a_stock.a_stock_data.sectors import industry_fund_flow
    industry_flow, iflow_err = _fetch_industry_flow(
        lambda: industry_fund_flow(top_n=10), retries=2)
    if industry_flow:
        result["industry_flow"] = industry_flow
    elif iflow_err:
        result["industry_flow_error"] = iflow_err
        try:
            push("⚠ 行业资金流缺失", f"盘后拉取失败: {iflow_err[:80]}",
                 subtitle="close_scan")
        except Exception:
            pass

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
                (date, close_at, sector_rotation, sentiment, candidates, industry_flow, status)
                VALUES (?,?,?,?,?,?,?)
            """, (today, result["close_at"],
                  json.dumps(sector_data, ensure_ascii=False),
                  json.dumps(result.get("sentiment"), ensure_ascii=False),
                  json.dumps(candidates, ensure_ascii=False, default=str),
                  json.dumps(industry_flow, ensure_ascii=False, default=str) if industry_flow else None,
                  "ok"))
        # 推送盘后摘要
        body_parts = []
        if sector_data:
            body_parts.append(f"板块:{sector_data['verdict']}")
        if result.get("sentiment"):
            body_parts.append(f"情绪:{result['sentiment']['temp']}({result['sentiment']['mood']})")
        if regime_data:
            body_parts.append(f"市场结构:{regime_data['level']}(派发{regime_data['dist_count']})")
        if industry_flow and industry_flow.get("inflow_top") and industry_flow.get("outflow_top"):
            top_in = industry_flow["inflow_top"][0]
            top_out = industry_flow["outflow_top"][0]
            body_parts.append(f"流入:{top_in['name']}{top_in['net_flow_yi']:+.0f}亿 流出:{top_out['name']}{top_out['net_flow_yi']:+.0f}亿")
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
    if r.get("regime"):
        rg = r["regime"]
        ftd_s = f" FTD:{rg['ftd']['date']}" if rg.get("ftd") else ""
        print(f"市场结构: {rg['level']} (派发日{rg['dist_count']}{ftd_s})")
    if r.get("industry_flow"):
        iflow = r["industry_flow"]
        print(f"行业资金流 (共{iflow.get('total',0)}行业):")
        print("  净流入TOP5:")
        for s in iflow.get("inflow_top", [])[:5]:
            print(f"    {s['name']:<12} 涨{s['change_pct']:+.2f}% 净流{s['net_flow_yi']:+.2f}亿")
        print("  净流出TOP5:")
        for s in iflow.get("outflow_top", [])[:5]:
            print(f"    {s['name']:<12} 涨{s['change_pct']:+.2f}% 净流{s['net_flow_yi']:+.2f}亿")
    if r.get("candidates"):
        print(f"持仓评分 top:")
        for c in sorted(r["candidates"], key=lambda x: x["total"], reverse=True)[:5]:
            print(f"  {c['name']} {c['total']} {c['level']}")


if __name__ == "__main__":
    main()
