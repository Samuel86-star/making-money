"""宏观日历: 政治局/中报/美联储/重大事件, JSON 存储 + CLI 查询."""
import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
import a_stock.config as cfg

MACRO_FILE = cfg.DATA_DIR / "macro_events.json"


def _load_events() -> list[dict]:
    if not MACRO_FILE.exists():
        return []
    return json.loads(MACRO_FILE.read_text())


def _save_events(events: list[dict]) -> None:
    MACRO_FILE.write_text(json.dumps(events, ensure_ascii=False, indent=2))


def _seed_2026() -> list[dict]:
    """2026 下半年关键事件 (种子数据)."""
    return [
        {"date": "2026-07-15", "kind": "data",   "name": "二季度GDP/社零", "impact": "high",
         "watch": "消费/政策预期", "action": "关注消费ETF"},
        {"date": "2026-07-22", "kind": "policy", "name": "政治局会议(年中)", "impact": "high",
         "watch": "财政/货币/地产/消费", "action": "事件前 7/15-7/21 降仓"},
        {"date": "2026-07-30", "kind": "fed",    "name": "美联储FOMC", "impact": "high",
         "watch": "鲍威尔讲话/利率", "action": "关注北向"},
        {"date": "2026-08-15", "kind": "earnings","name": "恒瑞医药中报", "impact": "high",
         "watch": "创新药占比/营收", "action": "8/15前后持有"},
        {"date": "2026-08-30", "kind": "earnings","name": "创业板权重股中报", "impact": "mid",
         "watch": "宁德/东财/迈瑞", "action": "影响159915"},
        {"date": "2026-09-30", "kind": "checkpoint","name": "Q3 强平再平衡", "impact": "self",
         "watch": "组合偏离度", "action": "若>85%股票则减仓"},
        {"date": "2026-10-01", "kind": "holiday","name": "国庆假期", "impact": "low",
         "watch": "假期外围", "action": "提前规划"},
        {"date": "2026-10-15", "kind": "earnings","name": "三季报预告披露截止", "impact": "high",
         "watch": "全市场预喜率", "action": "调仓窗口"},
        {"date": "2026-10-31", "kind": "earnings","name": "三季报正式披露", "impact": "high",
         "watch": "业绩验证", "action": "持仓复盘"},
        {"date": "2026-11-05", "kind": "fed",    "name": "美联储FOMC + 大选", "impact": "high",
         "watch": "美国政策+利率", "action": "关注半导体"},
        {"date": "2026-12-15", "kind": "fed",    "name": "美联储FOMC(末次)", "impact": "high",
         "watch": "2027展望", "action": "影响全年估值"},
        {"date": "2026-12-31", "kind": "checkpoint","name": "年终目标验收", "impact": "self",
         "watch": "100k目标", "action": "复盘 + 计划明年"},
    ]


def add(date_str: str, kind: str, name: str, impact: str = "mid",
        watch: str = "", action: str = "") -> None:
    events = _load_events()
    events.append({
        "date": date_str, "kind": kind, "name": name,
        "impact": impact, "watch": watch, "action": action,
        "created_at": datetime.now().isoformat(),
    })
    events.sort(key=lambda e: e["date"])
    _save_events(events)
    print(f"✓ 已添加: {date_str} {name}")


def list_events(days_ahead: int = 90, impact: str | None = None) -> list[dict]:
    events = _load_events()
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    out = []
    for e in events:
        d = datetime.strptime(e["date"], "%Y-%m-%d").date()
        if d < today - timedelta(days=7):
            continue
        if d > cutoff:
            continue
        if impact and e.get("impact") != impact:
            continue
        days_to = (d - today).days
        e["days_to"] = days_to
        e["urgency"] = "🔴" if days_to <= 3 else ("🟡" if days_to <= 14 else "🟢")
        out.append(e)
    return sorted(out, key=lambda e: e["date"])


def seed() -> None:
    events = _load_events()
    if events:
        print(f"已有 {len(events)} 条事件, 跳过 seed (--force 覆盖)")
        return
    _save_events(_seed_2026())
    print(f"✓ 已植入 {_seed_2026().__len__()} 条种子事件")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("--days", type=int, default=90)
    p_list.add_argument("--impact", choices=["high", "mid", "low", "self"])
    p_list.add_argument("--json", action="store_true")

    p_add = sub.add_parser("add")
    p_add.add_argument("--date", required=True)
    p_add.add_argument("--kind", default="event", choices=["data", "policy", "fed", "earnings", "holiday", "checkpoint", "event"])
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--impact", default="mid", choices=["high", "mid", "low", "self"])
    p_add.add_argument("--watch", default="")
    p_add.add_argument("--action", default="")

    p_seed = sub.add_parser("seed")

    args = ap.parse_args()

    if args.cmd == "seed":
        seed()
    elif args.cmd == "add":
        add(args.date, args.kind, args.name, args.impact, args.watch, args.action)
    elif args.cmd == "list":
        events = list_events(args.days, args.impact)
        if not events:
            print("近 90 天无事件. 运行 'python -m a_stock.macro_calendar seed' 植入种子")
            return
        print(f"\n=== 宏观事件 ({len(events)} 条, {args.days} 天内) ===\n")
        print(f"{'急':<4} {'日期':<12} {'类型':<10} {'强度':<6} {'事件':<22} {'关注点':<20} {'行动'}")
        for e in events:
            print(f"{e['urgency']:<4} {e['date']:<12} {e['kind']:<10} {e['impact']:<6} "
                  f"{e['name'][:22]:<22} {e['watch'][:20]:<20} {e['action'][:30]}")
        if args.json:
            print()
            print(json.dumps(events, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
