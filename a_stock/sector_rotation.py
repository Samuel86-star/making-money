"""板块轮动持续性: 四指标判断主线行情.
抄 quantdash fetch_sector_snapshots.py:131-199, 加强资金流 (quantdash 局限: 只看pctChange).

四指标:
  streakDays            同板块连续领涨天数
  topThreeAppearances   5日内进top3次数
  strengthDelta         涨势加速 (leader.pctChange - prev)
  strongestRepeat       真主线 (5日top3出现最多)

加强: 加 net_flow 连续性 (quantdash 没有)"""
import argparse
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
import a_stock.config as cfg
from a_stock.a_stock_data import industry_comparison

HISTORY_DB = cfg.DATA_DIR / "sector_rotation.sqlite"


@dataclass
class SectorEntry:
    date: str
    leader_name: str
    leader_code: str
    leader_pct_change: float
    streak_days: int
    top_three_appearances: int
    strength_delta: Optional[float]
    net_flow_yi: float  # 加强: 板块净流(亿)


@dataclass
class RotationResult:
    board_type: str
    current_leader: str
    current_streak_days: int
    current_top3_appearances: int
    strongest_repeat_name: str
    strongest_repeat_count: int
    entries: list = field(default_factory=list)
    verdict: str = ""  # 持续主线 / 轮动 / 衰退


def _init_db() -> None:
    with sqlite3.connect(str(HISTORY_DB)) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS sector_daily (
                date TEXT NOT NULL,
                rank INTEGER NOT NULL,
                name TEXT NOT NULL,
                code TEXT,
                change_pct REAL,
                net_flow REAL,
                leader TEXT,
                UNIQUE(date, name)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_date ON sector_daily(date)")


def snapshot_today() -> dict:
    """拉今日板块排名, 存DB. 返回 top3."""
    _init_db()
    today = date.today().isoformat()
    ic = industry_comparison(top_n=20)
    top = ic.get("top", [])
    if not top:
        return {"date": today, "top3": [], "saved": 0}

    with sqlite3.connect(str(HISTORY_DB)) as c:
        for s in top:
            # industry_comparison net_flow 已是元口径 (f62), /1e8 得亿
            raw = s["net_flow"] or 0
            nf_yi = raw / 1e8
            c.execute("""
                INSERT OR REPLACE INTO sector_daily
                (date, rank, name, code, change_pct, net_flow, leader)
                VALUES (?,?,?,?,?,?,?)
            """, (today, s["rank"], s["name"], s["code"],
                  s["change_pct"], nf_yi, s.get("leader", "")))

    return {"date": today, "top3": top[:3], "saved": len(top)}


def _load_history(days: int = 5) -> list[dict]:
    """加载最近N天板块排名历史."""
    _init_db()
    with sqlite3.connect(str(HISTORY_DB)) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("""
            SELECT date, rank, name, code, change_pct, net_flow, leader
            FROM sector_daily
            WHERE date >= date('now', ?)
            ORDER BY date ASC, rank ASC
        """, (f"-{days + 2} days",)).fetchall()

    # 按日期分组
    by_date = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(dict(r))
    # 取最近 days 天, 每天按 change_pct 降序 (rank可能不准)
    sorted_dates = sorted(by_date.keys())[-days:]
    return [{"date": d, "boards": sorted(by_date[d], key=lambda x: -(x["change_pct"] or 0))}
            for d in sorted_dates]


def analyze(board_type: str = "industry") -> Optional[RotationResult]:
    """四指标持续性分析. 抄 quantdash build_sector_persistence_data, 加资金流."""
    history = _load_history(days=5)
    if len(history) < 2:
        return None

    # 每日 top3 计数
    top3_count = {}
    for day in history:
        for b in day["boards"][:3]:
            top3_count[b["name"]] = top3_count.get(b["name"], 0) + 1

    entries = []
    for idx, day in enumerate(history):
        boards = day["boards"]
        if not boards:
            continue
        leader = boards[0]
        # streakDays: 往前数连续领涨
        streak = 1
        for cursor in range(idx - 1, -1, -1):
            prev = history[cursor]["boards"][0] if history[cursor]["boards"] else None
            if prev and prev["name"] == leader["name"]:
                streak += 1
            else:
                break
        # strengthDelta: 涨势加速
        prev_leader = history[idx - 1]["boards"][0] if idx > 0 and history[idx - 1]["boards"] else None
        strength_delta = (
            round(leader["change_pct"] - prev_leader["change_pct"], 2)
            if prev_leader and prev_leader["name"] == leader["name"]
            else None
        )
        entries.append(SectorEntry(
            date=day["date"],
            leader_name=leader["name"],
            leader_code=leader.get("code", ""),
            leader_pct_change=round(leader["change_pct"] or 0, 2),
            streak_days=streak,
            top_three_appearances=top3_count.get(leader["name"], 1),
            strength_delta=strength_delta,
            net_flow_yi=round(leader.get("net_flow") or 0, 2),
        ))

    if not entries:
        return None

    # 真主线: 5日top3出现最多
    strongest = sorted(top3_count.items(), key=lambda x: (-x[1], x[0]))[0]
    current = entries[-1]

    result = RotationResult(
        board_type=board_type,
        current_leader=current.leader_name,
        current_streak_days=current.streak_days,
        current_top3_appearances=current.top_three_appearances,
        strongest_repeat_name=strongest[0],
        strongest_repeat_count=strongest[1],
        entries=entries,
    )

    # 判定 (加强: 资金流连续性)
    result.verdict = _verdict(current, strongest, entries)
    return result


def _verdict(current: SectorEntry, strongest: tuple, entries: list) -> str:
    """判定: 持续主线 / 轮动 / 衰退."""
    # 持续主线: 连续领涨≥2 + top3出现≥3 + 涨势加速 + 资金流入
    if (current.streak_days >= 2
            and current.top_three_appearances >= 3
            and (current.strength_delta is None or current.strength_delta >= 0)
            and current.net_flow_yi > 0):
        return "🔥 持续主线"

    # 衰退: 领涨板块换 + 资金流出
    if current.streak_days == 1 and current.net_flow_yi < 0:
        return "🧊 衰退/轮动"

    # 轮动: 领涨换但资金还行
    if current.streak_days == 1:
        return "🔄 轮动中"

    return "📊 观望"


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("snapshot")
    sub.add_parser("analyze")
    p_json = sub.add_parser("json")

    args = ap.parse_args()

    if args.cmd == "snapshot":
        r = snapshot_today()
        print(f"✓ {r['date']} 存 {r['saved']} 个板块")
        print("今日 top3:")
        for s in r["top3"]:
            raw = s["net_flow"] or 0
            print(f"  {s['name']} {s['change_pct']:+.2f}% 净流{raw/1e8:+.2f}亿")
    elif args.cmd == "analyze":
        r = analyze()
        if not r:
            print("历史不足2天, 先跑 snapshot")
            return
        print(f"\n=== 板块轮动持续性 ===")
        print(f"判定: {r.verdict}")
        print(f"当前领涨: {r.current_leader} (连涨{r.current_streak_days}天, top3出现{r.current_top3_appearances}次)")
        print(f"真主线: {r.strongest_repeat_name} (5日top3出现{r.strongest_repeat_count}次)")
        print(f"\n5日明细:")
        print(f"{'日期':<12} {'领涨':<14} {'涨幅':<8} {'连涨':<6} {'top3':<6} {'加速':<8} {'净流亿'}")
        for e in r.entries:
            sd = f"{e.strength_delta:+.2f}" if e.strength_delta is not None else "-"
            print(f"{e.date:<12} {e.leader_name[:14]:<14} {e.leader_pct_change:<+8.2f} "
                  f"{e.streak_days:<6} {e.top_three_appearances:<6} {sd:<8} {e.net_flow_yi:+.2f}")
    elif args.cmd == "json":
        r = analyze()
        if r:
            print(json.dumps({
                "verdict": r.verdict,
                "current_leader": r.current_leader,
                "streak_days": r.current_streak_days,
                "strongest_repeat": r.strongest_repeat_name,
            }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
