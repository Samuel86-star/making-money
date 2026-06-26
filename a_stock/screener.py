#!/usr/bin/env python3
"""Screener v2:全市场扫描 + 短线/中线双轨。"""
import argparse
import json
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path
import a_stock.config as cfg
import a_stock.db as db
from a_stock.a_screen.sector_scan import scan_sectors
from a_stock.a_screen.candidate_filter import initial_filter, score_candidate
from a_stock.a_stock_data import (
    industry_comparison, ths_hot_reason, daily_dragon_tiger,
    tencent_quote, eastmoney_concept_blocks, stock_fund_flow_120d,
    eastmoney_reports,
)

PUSH2_CLIST = "https://push2.eastmoney.com/api/qt/clist/get"


def fetch_market_stocks(top_n: int = 200) -> list[dict]:
    """Step 2:push2 clist 全市场。"""
    import requests
    from a_stock.a_stock_data._common import retry
    fs = "m:0+t:6+f:!50,m:0+t:80+f:!50,m:0+t:81+f:!50,m:0+t:82+f:!50"
    fields = "f12,f14,f2,f3,f62,f66,f72"
    url = (
        f"{PUSH2_CLIST}?pn=1&pz={top_n}&po=1&np=1"
        f"&ut=bd1d9ddb04089700cf9c27f6f7426281"
        f"&fltt=2&invt=2&fid=f62&fs={fs}&fields={fields}"
    )
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}

    def _do():
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        return r

    r = retry(_do)
    d = r.json().get("data", {})
    out = []
    for row in d.get("diff", []):
        out.append({
            "code": row.get("f12", ""),
            "name": row.get("f14", ""),
            "price": row.get("f2", 0) or 0,
            "change_pct": row.get("f3", 0) or 0,
            "net_flow": (row.get("f62") or 0) * 10000,  # 万→元
            "inflow": (row.get("f66") or 0) * 10000,
            "outflow": (row.get("f72") or 0) * 10000,
        })
    return out


def enrich(stocks: list[dict], strategy: str, trade_date: str) -> list[dict]:
    """Step 4:em_get 防封逐股 enrichment(估值批量拉取)。"""
    # 批量拉取 tencent_quote 一次
    codes = [s["code"] for s in stocks]
    try:
        tq_batch = tencent_quote(codes)
    except Exception:
        tq_batch = {}

    enriched = []
    for s in stocks:
        code = s["code"]
        try:
            blocks = eastmoney_concept_blocks(code)
            s["sector"] = blocks["industries"][0]["name"] if blocks.get("industries") else ""
            s["concept_primary"] = blocks["concepts"][0]["name"] if blocks.get("concepts") else ""

            flows = stock_fund_flow_120d(code)
            s["fund_flow_20d"] = sum(r.get("main", 0) for r in flows[:20])

            reports = eastmoney_reports(code, max_pages=1)
            recent_7d = [r for r in reports if r.get("date", "") >= _date_offset(trade_date, -7)]
            s["report_count_7d"] = len(recent_7d)

            tq = tq_batch.get(code, {})
            s["pe_ttm"] = tq.get("pe_ttm", 0)
            s["pb"] = tq.get("pb", 0)
            s["mcap_yi"] = tq.get("mcap_yi", 0)
            s["turnover_pct"] = tq.get("turnover_pct", 0)
        except Exception as e:
            print(f"  ⚠ {code} enrich 失败:{e}", file=sys.stderr)
            s.setdefault("data_quality", "partial")
        enriched.append(s)
    return enriched


def run(trade_date: str, strategies: list[str], top_n: int, enrich_top: int, force: bool):
    print(f"⏳ Screener @ {trade_date} 策略={strategies}", flush=True)
    t0 = time.time()

    db.init_screener_db()

    # Step 1:市场级
    print("  Step 1: 行业板块...", end=" ", flush=True)
    sectors = scan_sectors(trade_date)
    print(f"行业 {len(sectors.get('industry', []))}, 热点 {len(sectors.get('hot', []))}, 龙虎榜 {len(sectors.get('dragon_tiger', []))}")

    # 落盘 sector_history
    for i, s in enumerate(sectors.get("industry", [])):
        db.upsert_sector(
            trade_date, "industry", s.get("name", ""),
            change_pct=s.get("change_pct", 0),
            net_flow=s.get("net_flow", 0),
            leader_name=s.get("leader", ""),
            leader_code="",
            rank=i + 1,
        )
    for i, s in enumerate(sectors.get("concept", [])):
        db.upsert_sector(
            trade_date, "concept", s.get("name", ""),
            change_pct=s.get("change_pct", 0),
            net_flow=s.get("net_flow", 0),
            leader_name=s.get("leader", ""),
            leader_code="",
            rank=i + 1,
        )

    # Step 2:全市场
    print("  Step 2: 全市场 clist...", end=" ", flush=True)
    raw = fetch_market_stocks(top_n=top_n)
    print(f"{len(raw)} 只")

    # Step 2b:批量拉取 PE/市值,供中线初筛使用
    if "mid" in strategies:
        raw_codes = [s["code"] for s in raw]
        try:
            tq_all = tencent_quote(raw_codes)
            for s in raw:
                tq = tq_all.get(s["code"], {})
                s["pe_ttm"] = tq.get("pe_ttm", 0)
                s["pb"] = tq.get("pb", 0)
                s["mcap_yi"] = tq.get("mcap_yi", 0)
                s["turnover_pct"] = tq.get("turnover_pct", 0)
        except Exception as e:
            print(f"\n  ⚠ 批量估值拉取失败:{e}", file=sys.stderr)

    # Step 3:各策略初筛
    candidates_by_strategy = {}
    for strat in strategies:
        cand = initial_filter(raw, strat)
        candidates_by_strategy[strat] = cand[:enrich_top]
        print(f"  Step 3[{strat}]: {len(cand)} → top {len(candidates_by_strategy[strat])}")

    # Step 4:enrichment
    print("  Step 4: enrichment...", end=" ", flush=True)
    for strat, cands in candidates_by_strategy.items():
        candidates_by_strategy[strat] = enrich(cands, strat, trade_date)
    print(f"done in {time.time()-t0:.0f}s")

    # Step 5:评分
    print("  Step 5: 评分...", end=" ", flush=True)
    for strat, cands in candidates_by_strategy.items():
        for c in cands:
            c["score"] = score_candidate(c, strat, sectors)
        cands.sort(key=lambda x: x.get("score", 0) or 0, reverse=True)

    # Step 6:落盘
    out_dir = cfg.DAILY_DIR / trade_date
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "sectors.json").write_text(json.dumps(sectors, ensure_ascii=False, indent=2, default=str))

    for strat, cands in candidates_by_strategy.items():
        (out_dir / f"candidates_{strat}.json").write_text(
            json.dumps(cands, ensure_ascii=False, indent=2, default=str)
        )
        for c in cands:
            db.upsert_candidate(
                trade_date, strat, c["code"],
                name=c.get("name"),
                sector=c.get("sector", ""),
                concept_primary=c.get("concept_primary", ""),
                net_flow=c.get("net_flow", 0),
                change_pct=c.get("change_pct", 0),
                pe_ttm=c.get("pe_ttm", 0),
                pb=c.get("pb", 0),
                mcap_yi=c.get("mcap_yi", 0),
                turnover_pct=c.get("turnover_pct", 0),
                report_count_7d=c.get("report_count_7d", 0),
                hot_reason="",
                on_dragon_tiger=int(any(dt.get("code") == c["code"] for dt in sectors.get("dragon_tiger", []))),
                score=c.get("score", 0),
                raw_data_path=str(out_dir / f"candidates_{strat}.json"),
            )

    db.upsert_daily_summary(
        trade_date,
        generated_at=datetime.now().isoformat(),
        short_count=len(candidates_by_strategy.get("short", [])),
        mid_count=len(candidates_by_strategy.get("mid", [])),
        sector_count=len(sectors.get("industry", [])),
        report_path=str(out_dir / "report.html"),
        status="ok",
    )
    print(f"\n✓ 完成 {time.time()-t0:.0f}s → {out_dir}")


def _date_offset(date_str: str, days: int) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return (d + timedelta(days=days)).strftime("%Y-%m-%d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--strategy", choices=["short", "mid", "both"], default="both")
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--enrich-top", type=int, default=30)
    ap.add_argument("--no-html", action="store_true")
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.render_only:
        render_html(args.date)
        return

    strategies = ["short", "mid"] if args.strategy == "both" else [args.strategy]
    run(args.date, strategies, args.top_n, args.enrich_top, args.force)


def render_html(trade_date: str):
    """从 SQLite 读 daily_summary + candidate_history,渲染 report.html。"""
    out_dir = cfg.DAILY_DIR / trade_date
    out_dir.mkdir(parents=True, exist_ok=True)
    with db.conn(cfg.SCREENER_DB) as c:
        sectors = c.execute(
            "SELECT * FROM sector_history WHERE scan_date=? AND sector_type='industry' ORDER BY net_flow DESC LIMIT 15",
            (trade_date,)).fetchall()
        concepts = c.execute(
            "SELECT * FROM sector_history WHERE scan_date=? AND sector_type='concept' ORDER BY net_flow DESC LIMIT 15",
            (trade_date,)).fetchall()
        short = c.execute(
            "SELECT * FROM candidate_history WHERE scan_date=? AND strategy='short' ORDER BY score DESC LIMIT 20",
            (trade_date,)).fetchall()
        mid = c.execute(
            "SELECT * FROM candidate_history WHERE scan_date=? AND strategy='mid' ORDER BY score DESC LIMIT 20",
            (trade_date,)).fetchall()

    html = ['<!doctype html><html><head><meta charset="utf-8"><title>Screener Report</title>',
            '<style>body{font-family:sans-serif;max-width:1200px;margin:20px auto;padding:0 20px;}',
            'table{border-collapse:collapse;width:100%;margin:10px 0;}',
            'th,td{border:1px solid #ddd;padding:6px 10px;text-align:left;}',
            'th{background:#f5f5f5;}',
            'h1,h2{color:#333;} .pos{color:#c00;} .neg{color:#0a0;}</style></head><body>']
    html.append(f"<h1>Screener 日报 {trade_date}</h1>")

    html.append("<h2>行业板块资金流 TOP15</h2><table><tr><th>行业</th><th>涨跌幅</th><th>净流入(亿)</th><th>领涨股</th></tr>")
    for s in sectors:
        nf = (s["net_flow"] or 0) / 1e8
        html.append(f"<tr><td>{s['name']}</td><td>{s['change_pct']:+.2f}%</td>"
                    f"<td>{nf:+.2f}</td><td>{s['leader_name'] or ''}</td></tr>")
    html.append("</table>")

    html.append("<h2>概念板块资金流 TOP15</h2><table><tr><th>概念</th><th>涨跌幅</th><th>净流入(亿)</th><th>领涨股</th></tr>")
    for s in concepts:
        nf = (s["net_flow"] or 0) / 1e8
        html.append(f"<tr><td>{s['name']}</td><td>{s['change_pct']:+.2f}%</td>"
                    f"<td>{nf:+.2f}</td><td>{s['leader_name'] or ''}</td></tr>")
    html.append("</table>")

    for strat_name, rows in [("短线 TOP20", short), ("中线 TOP20", mid)]:
        html.append(f"<h2>{strat_name}</h2><table><tr><th>代码</th><th>名称</th><th>行业</th>"
                    "<th>涨跌幅</th><th>净流入(亿)</th><th>PE</th><th>7日研报</th><th>评分</th></tr>")
        for r in rows:
            nf = (r["net_flow"] or 0) / 1e8
            html.append(f"<tr><td>{r['code']}</td><td>{r['name'] or ''}</td><td>{r['sector'] or ''}</td>"
                        f"<td>{r['change_pct']:+.2f}%</td><td>{nf:+.2f}</td>"
                        f"<td>{r['pe_ttm'] or 0:.1f}</td><td>{r['report_count_7d'] or 0}</td>"
                        f"<td><b>{r['score'] or 0:.1f}</b></td></tr>")
        html.append("</table>")

    html.append("</body></html>")
    (out_dir / "report.html").write_text("\n".join(html))
    print(f"✓ 渲染 → {out_dir / 'report.html'}")


if __name__ == "__main__":
    main()