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

    # 1. 全市场拉资金流 top — 降级链: 东财push2(主) → 新浪(备) → no_market_data
    source = "东财push2"
    try:
        stocks = fetch_market_stocks(top_n=top_n)
    except Exception as e:
        print(f"⚠ 东财push2 异常: {e}")
        stocks = []
    if not stocks:
        # 东财失败 → 新浪备用源 (真非东财, 东财挂时不受影响)
        print("  → 降级新浪备用源")
        try:
            from a_stock.a_stock_data.sina import fetch_market_fund_flow_rank
            stocks = fetch_market_fund_flow_rank(top_n=top_n)
            if stocks:
                source = "新浪(备用)"
        except Exception as e:
            print(f"⚠ 新浪备用源异常: {e}")
            stocks = []
    if not stocks:
        print("⚠ 东财+新浪均失败, 跳过本次扫描")
        return {"error": "no_market_data"}
    print(f"  拉到 {len(stocks)} 只候选 (资金流 top{top_n}, 来源:{source})")

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

    # 2b. Turtle 突破注入 (Donchian 突破=高确信趋势入场, sys2+8/sys1+5)
    n_turtle = _turtle_enrich(scored)
    if n_turtle:
        print(f"  🐢 Turtle 突破命中 {n_turtle}/{len(scored)} 只候选")

    # 3. 按 (总分, 资金流) 排序, veto 的排除
    valid = [s for s in scored if not s.get("veto")]
    valid.sort(key=lambda x: (x["total"], x.get("net_flow_yi", 0)), reverse=True)

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

    # 4b. 市场结构过滤 (audit 🟡4: SEVERE/HIGH市场只推中性及以下, 不追多)
    market_level = "NORMAL"
    try:
        from a_stock.market_regime import regime
        market_level = regime("159915")["level"]
    except Exception:
        pass
    if market_level in ("HIGH", "SEVERE"):
        before = len(valid)
        # 白名单: 防御市场只留观望中性/偏弱可蹲 (不追偏多/重仓)
        DEFENSIVE_LEVELS = ("观望中性", "偏弱可蹲")
        valid = [s for s in valid if any(lv in s.get("level", "") for lv in DEFENSIVE_LEVELS)]
        valid.sort(key=lambda x: (x["total"], x.get("net_flow_yi", 0)), reverse=True)
        filtered_out = before - len(valid)
        if filtered_out > 0:
            print(f"  ⚠ 市场结构 {market_level}, 过滤追多股: {before}→{len(valid)} (滤除{filtered_out}只)")

    # 4c. 切 top (4b过滤后再取)
    top = valid[:score_top]

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

    # 7b. 写 candidate_history 表 (供 backtest_hypothesis / 假设[A][B][C]回测)
    if top and not dry_run:
        n = _persist_candidates(date.today().isoformat(), top)
        print(f"  ✓ candidate_history 写入 {n}/{len(top)} 条")

    return {"candidates": len(top), "sector": sector,
            "top": [{"code": t["code"], "name": t["name"],
                     "total": t["total"], "level": t["level"]} for t in top]}


def _turtle_enrich(scored: list) -> int:
    """Turtle 突破信号注入候选: 命中加 total + 标 turtle 字段.

    sys2 (55日突破) +8 / sys1 (20日突破) +5 — 高确信趋势入场, 直接抬排名.
    每候选跑 turtle.analyze (需 OHLCV parquet, 缺则跳过).
    返回命中数. 全程防御: 异常不影响其他候选."""
    try:
        from a_stock import turtle
    except Exception:
        return 0
    hit = 0
    for d in scored:
        try:
            t = turtle.analyze(d["code"])
            if t and t.signal:
                boost = 8 if t.signal == "sys2_breakout" else 5
                d["total"] = d.get("total", 0) + boost
                d["turtle"] = {
                    "signal": t.signal,
                    "entry": t.entry,
                    "stop": t.stop,
                    "unit_shares": t.unit_shares,
                    "atr": t.atr,
                }
                hit += 1
        except Exception:
            continue
    return hit


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
        line = (f"{i}. {t['name']}({t['code']}) {t['total']}分 {t['level']} "
                f"资金{t.get('net_flow_yi', 0):+.1f}亿")
        tk = t.get("turtle")
        if tk and tk.get("entry"):
            line += (f" 🐢{('S2' if tk['signal']=='sys2_breakout' else 'S1')}"
                     f"入{tk['entry']:.2f}/止损{tk['stop']:.2f}/{tk['unit_shares']}股")
        lines.append(line)
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


def _persist_candidates(trade_date: str, top: list, strategy: str = "mid") -> int:
    """写候选到 screener.candidate_history (供 backtest_hypothesis / 假设[A][B][C]回测).

    早期 morning_scan 只写 JSON + watchlist, 没写表 → candidate_history 一直空,
    到回测日无数据源可验 [A]强势入场/[B]surge不追/[C]scorer失效.
    字段映射: net_flow_yi(亿) → net_flow(元, ×1e8); total → score; level+资金 → hot_reason.
    strategy 默认 mid (morning_scan 候选不区分短中, 评分偏中线).
    """
    from a_stock import db
    n = 0
    for t in top:
        try:
            # sector 从评分 factors 取 (sector_scorer detail.industry), 无则 None
            sector = (t.get("factors", {})
                      .get("sector", {})
                      .get("detail", {})
                      .get("industry")) or None
            db.upsert_candidate(
                trade_date, strategy, t["code"],
                name=t.get("name"),
                sector=sector,
                net_flow=round((t.get("net_flow_yi") or 0) * 1e8),
                change_pct=t.get("change_pct"),
                score=t.get("total"),
                hot_reason=f"{t.get('level', '')} 资金{t.get('net_flow_yi', 0):+.1f}亿"
                           + (f" 🐢{t['turtle']['signal']}" if t.get("turtle") else ""),
            )
            n += 1
        except Exception as e:
            print(f"  ⚠ candidate_history 写入失败 {t.get('code')}: {e}")
    return n


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
