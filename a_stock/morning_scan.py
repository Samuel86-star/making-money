"""早盘扫描: 全市场扫描 + 多因子评分 + 板块轮动 → 推送候选.
9:35/9:50 cron 触发. 抄 aiagents-stock 多时间点思路, 但用现有 screener (东财push2批量, 比参考项目强).

非阻塞锁防重入 (LLM/评分易超时).
不抄 aiagents-stock: 假并行 / LLM-as-judge / pywencai单点依赖."""
import argparse
import json
import sqlite3
import threading
from datetime import datetime, date
from pathlib import Path
import a_stock.config as cfg
from a_stock.notifier import push
from a_stock.screener import fetch_market_stocks
from a_stock.scorers.total_scorer import score_candidate, to_dict

_lock = threading.Lock()


def scan(top_n: int = 20, score_top: int = 5, dry_run: bool = False) -> dict:
    """全市场扫描 → 评分 → top候选推送."""
    if not _lock.acquire(blocking=False):
        return {"error": "skipped_previous_running"}

    try:
        return _scan_impl(top_n, score_top, dry_run)
    finally:
        _lock.release()


def _scan_impl(top_n: int, score_top: int, dry_run: bool) -> dict:
    print(f"⏳ 早盘扫描 @ {datetime.now().strftime('%H:%M:%S')}")

    # 1. 全市场拉资金流 top (现有 screener, 东财push2)
    stocks = fetch_market_stocks(top_n=top_n)
    if not stocks:
        print("⚠ 拉取市场数据失败")
        return {"error": "no_market_data"}
    print(f"  拉到 {len(stocks)} 只候选 (资金流 top{top_n})")

    # === 策略层 (Signal Bridge): 策略候选 + screener 候选并集 ===
    strategy_codes = set()
    try:
        from a_stock.strategies.runner import run_top
        votes = run_top(stocks, top_m=20)
        strategy_codes = {v.code for v in votes}
        print(f"  策略层产出 {len(strategy_codes)} 只候选 (top confidence)")
        for v in votes[:5]:
            print(f"    {v.name}({v.code}) conf={v.total_confidence:.2f} "
                  f"[{','.join(v.strategies)}] {v.top_reason}")
    except Exception as e:
        print(f"  ⚠ 策略层失败, 回退纯 screener: {e}")
        strategy_codes = set()

    # 2. 多因子评分 — 策略候选 ∪ screener top10
    scored = []
    scored_codes = sorted(strategy_codes | {s["code"] for s in stocks[:10]})
    # 建 code→stock 映射 (策略产出的 code 可能不在 screener 前10, 用其 code 查 stock)
    stock_map = {s["code"]: s for s in stocks}
    for code in scored_codes:
        s = stock_map.get(code, {"code": code, "name": code,
                                 "net_flow": 0, "change_pct": 0})
        try:
            ts = score_candidate(s["code"], s.get("name", ""))
            d = to_dict(ts)
            d["net_flow_yi"] = (s.get("net_flow") or 0) / 1e8
            d["change_pct"] = s.get("change_pct", 0)
            scored.append(d)
        except Exception as e:
            print(f"  ⚠ {code} 评分失败: {e}")

    # 3. 按 (总分, 资金流) 排序, veto 的排除
    valid = [s for s in scored if not s.get("veto")]
    valid.sort(key=lambda x: (x["total"], x.get("net_flow_yi", 0)), reverse=True)
    top = valid[:score_top]

    # 4. 板块轮动
    from a_stock.sector_rotation import analyze as sector_analyze
    sector = None
    try:
        sr = sector_analyze()
        if sr:
            sector = {
                "verdict": sr.verdict,
                "current_leader": sr.current_leader,
                "strongest_repeat": sr.strongest_repeat_name,
            }
    except Exception as e:
        print(f"  ⚠ 板块轮动失败: {e}")

    # 5. 推送
    if top and not dry_run:
        _push_results(top, sector)

    # 6. 写 watchlist (候选池)
    if top and not dry_run:
        _save_to_watchlist(top)

    # 7. 落盘
    out_dir = cfg.DAILY_DIR / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "morning_scan.json").write_text(
        json.dumps({"candidates": top, "sector": sector,
                    "scanned_at": datetime.now().isoformat()},
                   ensure_ascii=False, indent=2, default=str))

    return {"candidates": len(top), "sector": sector,
            "top": [{"code": t["code"], "name": t["name"],
                     "total": t["total"], "level": t["level"]} for t in top]}


def _push_results(top: list, sector: dict | None) -> None:
    """推送候选 top5 + 板块."""
    # 板块轮动
    if sector:
        push("🔄 板块轮动",
             f"{sector['verdict']} | 领涨:{sector['current_leader']} | "
             f"主线:{sector['strongest_repeat']}",
             subtitle="早盘扫描")

    # 候选 top
    lines = []
    for i, t in enumerate(top, 1):
        lines.append(f"{i}. {t['name']}({t['code']}) {t['total']}分 {t['level']} "
                     f"资金{t.get('net_flow_yi', 0):+.1f}亿")
    body = "\n".join(lines)
    push("🎯 早盘候选", body, subtitle=f"top{len(top)}")


def _save_to_watchlist(top: list) -> None:
    """写 watchlist (候选池)."""
    from a_stock.a_screen.decision_log import add_to_watchlist
    for t in top:
        try:
            add_to_watchlist(t["code"], name=t["name"],
                             theme="早盘扫描候选",
                             note=f"评分{t['total']} {t['level']}")
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, default=20, help="市场拉取数")
    ap.add_argument("--score-top", type=int, default=5, help="评分后取top")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    result = scan(args.top_n, args.score_top, args.dry_run)
    if "error" in result:
        print(f"⚠ {result['error']}")
        return

    print(f"\n=== 早盘扫描结果 ===")
    if result.get("sector"):
        s = result["sector"]
        print(f"板块: {s['verdict']} 领涨{s['current_leader']} 主线{s['strongest_repeat']}")
    print(f"\n候选 top{len(result.get('top', []))}:")
    for t in result.get("top", []):
        print(f"  {t['name']}({t['code']}) {t['total']}分 {t['level']}")


if __name__ == "__main__":
    main()
