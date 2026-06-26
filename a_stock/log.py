#!/usr/bin/env python3
"""复盘决策记录 CLI。"""
import argparse
import sys
from datetime import date, datetime
import a_stock.config as cfg
import a_stock.db as db
from a_stock.a_screen.decision_log import add_buy, add_add, close, update_plan, list_open, get
from a_stock.a_screen.snapshot import load_snapshot


def _auto_brief_path(code: str) -> str | None:
    """检测今日 brief 路径,若存在则返回。"""
    p = cfg.BRIEFS_DIR / code / f"{date.today().isoformat()}.json"
    return str(p) if p.exists() else None


def cmd_buy(args):
    code = args.code
    # 简化模式 vs 显式
    if args.price is None:
        return _interactive_buy(code, args.strategy, args.plan_max_position_pct)

    brief_path = args.from_brief or _auto_brief_path(code)
    new_id = add_buy(
        code=code, strategy=args.strategy,
        price=args.price, quantity=args.qty,
        reason=args.reason, brief_snapshot_path=brief_path,
        plan_stop_loss=args.plan_stop_loss, plan_target=args.plan_target,
        plan_hold_days=args.plan_hold_days, plan_max_position_pct=args.plan_max_position_pct,
    )
    print(f"✓ 已记录 buy id={new_id}  brief={'已挂' if brief_path else '无'}")


def _interactive_buy(code: str, strategy: str, plan_max_pct: float | None):
    """简化模式:检测 brief,预填价格,交互式问其余。"""
    brief_path = _auto_brief_path(code)
    price = None
    if brief_path:
        snap = load_snapshot(code, date.today().isoformat())
        if snap:
            price = snap["fundamentals"].get("price")
            print(f"[检测到 brief] {snap['meta']['name']}({code}) 现价 {price}")

    if price is None:
        price = float(input(f"现价 [{code}]: "))

    qty = int(input(f"数量(股) [100]: ") or "100")
    reason = input("一句话理由: ")
    stop = float(input(f"计划止损 [{price*0.95:.2f}]: ") or str(price * 0.95))
    target = float(input(f"计划目标 [{price*1.10:.2f}]: ") or str(price * 1.10))
    hold = int(input("计划持有天数 [5]: ") or "5")
    max_pct = float(input(f"最大仓位 % [{plan_max_pct or 10}]: ") or str(plan_max_pct or 10))

    new_id = add_buy(
        code=code, strategy=strategy,
        price=price, quantity=qty,
        reason=reason, brief_snapshot_path=brief_path,
        plan_stop_loss=stop, plan_target=target,
        plan_hold_days=hold, plan_max_position_pct=max_pct,
    )
    print(f"\n✓ 已记录 buy id={new_id}")
    print(f"  strategy={strategy}  price={price}  qty={qty}")
    print(f"  plan: stop={stop} target={target} hold={hold}d max_pct={max_pct}%")
    print(f"  brief: {brief_path or '无'}")


def cmd_add(args):
    new_id = add_add(
        code=args.code, strategy=args.strategy,
        price=args.price, quantity=args.qty, reason=args.reason,
    )
    print(f"✓ 加仓 id={new_id}")


def cmd_close(args):
    close(args.id, args.close_date, args.close_price, args.close_reason)
    row = get(args.id)
    print(f"✓ 平仓 id={args.id}  pnl={row['pnl_pct']:+.2f}%")


def cmd_plan(args):
    fields = {k: v for k, v in vars(args).items()
              if k.startswith("plan_") and v is not None}
    if not fields:
        print("无 plan_ 前缀的参数可更新", file=sys.stderr)
        sys.exit(1)
    update_plan(args.id, **fields)
    print(f"✓ 更新 id={args.id}  plan={fields}")


def cmd_list(args):
    rows = list_open(args.strategy) if not args.all else _list_all(args.strategy, args.recent)
    if not rows:
        print("无记录")
        return
    print(f"{'id':>4}  {'code':<8}  {'name':<10}  {'strat':<6}  {'date':<10}  {'price':<8}  {'qty':<6}  {'close':<10}  {'pnl%':<7}")
    for r in rows[:args.recent]:
        print(f"{r['id']:>4}  {r['code']:<8}  {(r['name'] or ''):<10}  {r['strategy']:<6}  "
              f"{r['decision_date']:<10}  {r['price']:<8.2f}  {r['quantity']:<6}  "
              f"{(r['close_date'] or '-'):<10}  {(r['pnl_pct'] or 0):<+7.2f}")


def _list_all(strategy, recent):
    with db.conn(cfg.DECISIONS_DB) as c:
        return c.execute(
            "SELECT * FROM decisions WHERE strategy=? ORDER BY decision_date DESC LIMIT ?",
            (strategy, recent)).fetchall()


def cmd_show(args):
    row = get(args.id)
    if not row:
        print(f"无 id={args.id}")
        return
    for k in row.keys():
        print(f"  {k}: {row[k]}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_buy = sub.add_parser("buy")
    p_buy.add_argument("code")
    p_buy.add_argument("--strategy", choices=["short", "mid"], required=True)
    p_buy.add_argument("--price", type=float)
    p_buy.add_argument("--qty", type=int)
    p_buy.add_argument("--reason")
    p_buy.add_argument("--from-brief")
    p_buy.add_argument("--plan-stop", type=float, dest="plan_stop_loss")
    p_buy.add_argument("--plan-target", type=float, dest="plan_target")
    p_buy.add_argument("--plan-hold", type=int, dest="plan_hold_days")
    p_buy.add_argument("--plan-max-pct", type=float, dest="plan_max_position_pct")
    p_buy.set_defaults(func=cmd_buy)

    p_add = sub.add_parser("add")
    p_add.add_argument("code")
    p_add.add_argument("--strategy", choices=["short", "mid"], required=True)
    p_add.add_argument("--price", type=float, required=True)
    p_add.add_argument("--qty", type=int, required=True)
    p_add.add_argument("--reason")
    p_add.set_defaults(func=cmd_add)

    p_close = sub.add_parser("close")
    p_close.add_argument("id", type=int)
    p_close.add_argument("--close-date", required=True)
    p_close.add_argument("--close-price", type=float, required=True)
    p_close.add_argument("--close-reason", required=True, choices=["stop_loss", "target", "manual", "expired"])
    p_close.set_defaults(func=cmd_close)

    p_plan = sub.add_parser("plan")
    p_plan.add_argument("id", type=int)
    p_plan.add_argument("--plan-stop", type=float, dest="plan_stop_loss")
    p_plan.add_argument("--plan-target", type=float, dest="plan_target")
    p_plan.add_argument("--plan-hold", type=int, dest="plan_hold_days")
    p_plan.set_defaults(func=cmd_plan)

    p_list = sub.add_parser("list")
    p_list.add_argument("--open", action="store_true")
    p_list.add_argument("--all", action="store_true")
    p_list.add_argument("--strategy", choices=["short", "mid"])
    p_list.add_argument("--recent", type=int, default=20)
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show")
    p_show.add_argument("id", type=int)
    p_show.set_defaults(func=cmd_show)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()