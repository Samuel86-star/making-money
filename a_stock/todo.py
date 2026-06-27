"""待办功能: 跨会话记录"该做但还没做"的事, 时机到了提醒.
存储: data/todo.json. 优先按 due_date 排序."""
import argparse
import json
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
import a_stock.config as cfg

TODO_FILE = cfg.DATA_DIR / "todo.json"


def _load() -> list[dict]:
    if not TODO_FILE.exists():
        return []
    return json.loads(TODO_FILE.read_text())


def _save(items: list[dict]) -> None:
    TODO_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2))


def add(title: str, due: str | None = None, priority: str = "mid",
        context: str = "", command: str = "") -> str:
    """添加待办. due 格式 YYYY-MM-DD, priority: high/mid/low."""
    items = _load()
    item = {
        "id": uuid.uuid4().hex[:8],
        "title": title,
        "due": due,
        "priority": priority,
        "context": context,
        "command": command,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }
    items.append(item)
    _save(items)
    print(f"✓ [{item['id']}] {title}" + (f"  (due {due})" if due else ""))
    return item["id"]


def done(item_id: str) -> None:
    items = _load()
    for it in items:
        if it["id"] == item_id or it["id"].startswith(item_id):
            it["status"] = "done"
            it["done_at"] = datetime.now().isoformat()
            _save(items)
            print(f"✓ 完成: {it['title']}")
            return
    print(f"✗ 无 id={item_id}")


def remove(item_id: str) -> None:
    items = _load()
    new = [it for it in items if not (it["id"] == item_id or it["id"].startswith(item_id))]
    if len(new) < len(items):
        _save(new)
        print(f"✓ 已删除: {item_id}")
    else:
        print(f"✗ 无 id={item_id}")


def list_pending(days_ahead: int = 30, show_done: bool = False) -> list[dict]:
    items = _load()
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    out = []
    for it in items:
        if it["status"] == "done" and not show_done:
            continue
        if it["status"] == "done" and show_done:
            out.append(it)
            continue
        if it.get("due"):
            try:
                d = datetime.strptime(it["due"], "%Y-%m-%d").date()
            except ValueError:
                continue
            if d < today - timedelta(days=1):
                it["_status_label"] = "🔴已过期"
            elif d < today + timedelta(days=2):
                it["_status_label"] = "🟠今天/明天"
            elif d <= cutoff:
                it["_status_label"] = f"🟡{d.strftime('%m-%d')}"
            else:
                it["_status_label"] = f"🟢{d.strftime('%m-%d')}"
        else:
            it["_status_label"] = "  -"
        out.append(it)
    # 排序: pending 优先, 已 done 在后
    out.sort(key=lambda x: (x["status"] == "done",
                            x.get("due") or "9999-99-99",
                            {"high": 0, "mid": 1, "low": 2}.get(x.get("priority", "mid"), 1)))
    return out


def seed_default() -> None:
    """植入默认 11 条关键节点."""
    items = _load()
    if items:
        print(f"已有 {len(items)} 条, 跳过 seed (--force 覆盖)")
        return

    seeds = [
        ("测试 Mac 推送",                              None,        "high", "运行 notifier test 验证弹窗",       "python -m a_stock.notifier test"),
        ("装 cron 监控 (周一前)",                       None,        "high", "自动跑 monitor",                     "./a_stock/setup_cron.sh install"),
        ("周一开盘前检查 rules.yaml 阈值",              None,        "mid",  "根据周末舆情调整",                  "cat a_stock/rules.yaml"),
        ("周一 14:30 后评估 515880 试仓",               None,        "high", "≤1.70 加 3000 股",                  "python -m a_stock.monitor --dry-run"),
        ("7/15 前评估 515650 消费 ETF 加仓",            "2026-07-15","mid",  "跌到 0.93-0.95 加仓",              "python -m a_stock.position_sizer --method kelly"),
        ("7/15-7/21 政治局前减仓准备",                 "2026-07-20","high", "减仓到 70%",                        ""),
        ("7/22 政治局会议结果评估",                    "2026-07-22","high", "看财政/消费政策",                    "python -m a_stock.macro_calendar list --days 3"),
        ("8/15 恒瑞中报持仓决策",                      "2026-08-15","high", "中报占比 >63.5% 则加仓",            "python -m a_stock.monitor --dry-run"),
        ("8/30 创业板权重股中报",                       "2026-08-30","mid",  "影响 159915",                       ""),
        ("9/30 Q3 强平再平衡检查",                     "2026-09-30","high", "若股票 >85% 减到 70%",              "python -m a_stock.risk_metrics"),
        ("10/15 三季报预告披露截止",                    "2026-10-15","high", "调仓窗口",                          ""),
        ("10/31 三季报正式披露复盘",                    "2026-10-31","high", "持仓验证",                          ""),
        ("11/5 美联储 + 美国大选",                      "2026-11-05","high", "关注半导体",                        ""),
        ("12/15 美联储末次 FOMC",                      "2026-12-15","high", "2027 展望",                         ""),
        ("12/31 年终 100k 目标验收",                   "2026-12-31","high", "复盘 + 明年计划",                   "python -m a_stock.goal_sim"),
        ("每周日: 跑 goal_sim + risk + sentiment",     None,        "mid",  "周度复盘",                          "python -m a_stock.goal_sim && python -m a_stock.risk_metrics"),
    ]
    for title, due, pri, ctx, cmd in seeds:
        add(title, due, pri, ctx, cmd)
    print(f"\n✓ 植入 {len(seeds)} 条默认待办")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("--days", type=int, default=30)
    p_list.add_argument("--all", action="store_true", help="含已完成")

    p_add = sub.add_parser("add")
    p_add.add_argument("title")
    p_add.add_argument("--due")
    p_add.add_argument("--priority", choices=["high", "mid", "low"], default="mid")
    p_add.add_argument("--context", default="")
    p_add.add_argument("--command", default="")

    p_done = sub.add_parser("done")
    p_done.add_argument("id")

    p_rm = sub.add_parser("rm")
    p_rm.add_argument("id")

    p_seed = sub.add_parser("seed")

    args = ap.parse_args()

    if args.cmd == "list":
        items = list_pending(args.days, args.all)
        if not items:
            print("无待办. 运行 'python -m a_stock.todo seed' 植入默认")
            return
        print(f"\n=== 待办 ({len(items)} 条, {args.days} 天内) ===\n")
        print(f"{'ID':<10} {'状态':<10} {'优先':<5} {'日期':<8} {'任务':<30} {'命令'}")
        for it in items:
            print(f"{it['id']:<10} {it['_status_label']:<10} {it.get('priority',''):<5} "
                  f"{(it.get('due') or '-'):<8} {it['title'][:30]:<30} {it.get('command','')[:40]}")
    elif args.cmd == "add":
        add(args.title, args.due, args.priority, args.context, args.command)
    elif args.cmd == "done":
        done(args.id)
    elif args.cmd == "rm":
        remove(args.id)
    elif args.cmd == "seed":
        seed_default()


if __name__ == "__main__":
    main()
