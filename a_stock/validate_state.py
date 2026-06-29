#!/usr/bin/env python3
"""校验 PROJECT_STATE.md 持仓成本列与 decisions.sqlite 父lot买入价一致.

06-29教训: PROJECT_STATE 东财成本写成 20.07 (实为卖出价笔误), 真值 21.279,
导致 CFO 瞎猜成本错误判断. 本脚本从源头堵住 "文档成本 ≠ db 成本".

用法:
    .venv/bin/python -m a_stock.validate_state
    .venv/bin/python -m a_stock.validate_state --state data/PROJECT_STATE.md
"""
import re
import argparse
import sqlite3
from pathlib import Path
import a_stock.config as cfg


# 持仓表行: 代码(6位) 名称 数量 成本 市值
# 例: 600276  恒瑞医药          200  48.67    9,734
POSITION_RE = re.compile(
    r"^\s*(\d{6})\s+(\S+)\s+([\d,]+)\s+([\d.]+)\s+([\d,]+)\s*$"
)


def _parse_qty(s: str) -> int:
    return int(s.replace(",", ""))


def _load_db_costs() -> dict[str, float]:
    """从 decisions 表算每标的真实成本 (移动加权平均, lot 制剩余)."""
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    conn.row_factory = sqlite3.Row
    lots = conn.execute("""
        SELECT id, code, price, quantity FROM decisions
        WHERE action IN ('buy','add') AND close_date IS NULL
    """).fetchall()
    reduces = conn.execute("""
        SELECT parent_id, SUM(quantity) AS qty FROM decisions
        WHERE action='reduce' AND close_date IS NOT NULL
        GROUP BY parent_id
    """).fetchall()
    conn.close()
    red = {r["parent_id"]: r["qty"] for r in reduces}
    agg = {}
    for lot in lots:
        c = lot["code"]
        remaining = lot["quantity"] - red.get(lot["id"], 0)
        if remaining <= 0:
            continue
        if c not in agg:
            agg[c] = {"qty": 0, "cost_sum": 0.0}
        agg[c]["qty"] += remaining
        agg[c]["cost_sum"] += lot["price"] * remaining
    return {c: v["cost_sum"] / v["qty"] for c, v in agg.items() if v["qty"]}


def validate(state_path: Path) -> list[dict]:
    """返回不一致列表 [{code, state_cost, db_cost, diff_pct, line}]."""
    db_costs = _load_db_costs()
    mismatches = []
    for i, line in enumerate(state_path.read_text().splitlines(), 1):
        m = POSITION_RE.match(line)
        if not m:
            continue
        code, _name, qty_s, cost_s, _mv_s = m.groups()
        if code not in db_costs:
            continue  # 文档有但db无持仓 (可能已清仓), 跳过
        state_cost = float(cost_s)
        db_cost = db_costs[code]
        if db_cost <= 0:
            continue
        diff_pct = abs(state_cost - db_cost) / db_cost * 100
        if diff_pct > 0.5:  # 允许0.5%四舍五入误差
            mismatches.append({
                "code": code, "line": i,
                "state_cost": state_cost, "db_cost": round(db_cost, 4),
                "diff_pct": round(diff_pct, 2),
            })
    return mismatches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(cfg.DATA_DIR / "PROJECT_STATE.md"))
    args = ap.parse_args()
    state_path = Path(args.state)
    if not state_path.exists():
        print(f"❌ 找不到 {state_path}")
        return

    mismatches = validate(state_path)
    print(f"=== PROJECT_STATE 成本校验 ===")
    print(f"文档: {state_path}")
    if not mismatches:
        print("✅ 所有持仓成本与 db 一致")
        return
    print(f"❌ 发现 {len(mismatches)} 处不一致:")
    for m in mismatches:
        print(f"  行{m['line']} {m['code']}: 文档{m['state_cost']} vs db{m['db_cost']} "
              f"(差{m['diff_pct']}%)")
    print("\n修正: 以 db 为准, 更新 PROJECT_STATE 持仓表成本列")


if __name__ == "__main__":
    main()
