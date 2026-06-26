#!/usr/bin/env python3
"""Research Brief: 单股调研简报。"""
import argparse
import sys
from datetime import date
import a_stock.config as cfg
from a_stock.a_screen.brief_builder import build_snapshot, render_markdown
from a_stock.a_screen.snapshot import save_snapshot, save_markdown, load_snapshot


def single(code: str, trade_date: str, force: bool, strategy: str | None):
    """单股 brief。"""
    code = code.strip()
    snap = load_snapshot(code, trade_date, force=force)
    if snap is None:
        print(f"⏳ 拉 {code} 数据...", flush=True)
        snap = build_snapshot(code, trade_date, trigger="manual")
        save_snapshot(snap)
    md = render_markdown(snap)
    save_markdown(snap, md)
    print(md)
    print(f"\n💾 快照: {cfg.BRIEFS_DIR / code / trade_date}.json")
    print(f"   AI 分析待 Claude Code 填充; 调 update_ai_analysis() 写回。")


def batch_from_screener(trade_date: str, top_n: int):
    """从今日扫描的 top N 各策略自动生成。"""
    import a_stock.db as db
    db.init_screener_db()
    generated = 0
    with db.conn(cfg.SCREENER_DB) as c:
        for strat in ("short", "mid"):
            rows = c.execute(
                "SELECT code, name FROM candidate_history WHERE scan_date=? AND strategy=? ORDER BY score DESC LIMIT ?",
                (trade_date, strat, top_n)).fetchall()
            for r in rows:
                code = r["code"]
                if load_snapshot(code, trade_date) is not None:
                    continue
                try:
                    print(f"  brief {code}({r['name']})...", flush=True)
                    snap = build_snapshot(code, trade_date, trigger=f"from_screener_{strat}")
                    save_snapshot(snap)
                    md = render_markdown(snap)
                    save_markdown(snap, md)
                    generated += 1
                except Exception as e:
                    print(f"  ⚠ {code} 失败: {e}", file=sys.stderr)
    print(f"✓ 生成 {generated} 份 brief")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code", nargs="?", help="股票代码 (单股模式)")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--strategy", choices=["short", "mid"], help="强调某策略的字段")
    ap.add_argument("--from-screener", metavar="DATE_OR_TODAY",
                    help="从 screener 拉 top N 批量生成")
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.from_screener:
        d = date.today().isoformat() if args.from_screener == "today" else args.from_screener
        batch_from_screener(d, args.top_n)
    elif args.code:
        single(args.code, args.date, args.force, args.strategy)
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()