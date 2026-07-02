"""会话内盘面心跳: 每5min跑一次, caveman简报.

输出三块:
  组合: 时段 | 日内%(5min趋势) | 浮盈(趋势) | Heat | 触发/异动
  持仓: 每只 实价 + 5min价格趋势 + 浮盈
  进攻: edge_scanner 全市场进攻候选 (验证setup, 实时sizing)

状态: data/heartbeat_state.json 存上tick值, 本tick算 5min delta.
休市 → 一行🌙, 不跑数据.

被会话cron调用: `.venv/bin/python -m a_stock.heartbeat`
"""
import json
import re
import subprocess
import sys
from datetime import datetime

import a_stock.config as cfg
from a_stock.scheduler import trading_session
from a_stock.risk_metrics import _load_positions

STATE_FILE = cfg.DATA_DIR / "heartbeat_state.json"


def _run(module: str, *args: str) -> str:
    """跑 a_stock 子模块, 返回 stdout (超时90s)."""
    try:
        r = subprocess.run([sys.executable, "-m", module, *args],
                           capture_output=True, text=True, timeout=90)
        return r.stdout
    except Exception as e:
        return f"[err {module}: {e}]"


def _arrow(delta: float, fmt: str = "{:.2f}") -> str:
    """delta → ↑0.12 / ↓0.12 / →0."""
    if abs(delta) < 1e-9:
        return "→0"
    return ("↑" if delta > 0 else "↓") + fmt.format(abs(delta))


def _parse_monitor(out: str) -> dict:
    m = re.search(r"组合日内\s*([-\d.]+)%.*?规则触发\s*(\d+)\s*条.*?异动触发\s*(\d+)", out)
    if not m:
        return {}
    return {"day_pct": float(m.group(1)), "trig": int(m.group(2)), "anom": int(m.group(3))}


def _parse_risk(out: str) -> dict:
    pnl = re.search(r"合计浮盈:\s*([+-]?\d+)\s*元", out)
    heat = re.search(r"总风险:\s*[\d,]+\s*元\s*\(([\d.]+)%", out)
    return {"pnl": int(pnl.group(1)) if pnl else None,
            "heat_pct": float(heat.group(1)) if heat else None}


def _parse_offensive(out: str, top: int = 3) -> list[dict]:
    """解析 edge_scanner 表, 取 shares>0 的前 top."""
    rows = []
    for line in out.splitlines():
        m = re.match(
            r"^(\d{6})\s+(\S+)\s+(\S+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+"
            r"(\d+)\s+([\d.]+)%\s+([+-][\d.]+)%", line)
        if not m:
            continue
        shares = int(m.group(7))
        if shares <= 0:
            continue  # 价太高买不起一手, 跳过
        rows.append({"code": m.group(1), "name": m.group(2), "setup": m.group(3),
                     "entry": float(m.group(4)), "stop": float(m.group(5)),
                     "target": float(m.group(6)), "shares": shares,
                     "pct": float(m.group(8))})
    return rows[:top]


def _sector_flow(top: int = 3) -> str:
    """板块资金流(今日) top流入/流出. 拉取失败返回空串 (盘中push2抖动/盘后)."""
    try:
        from a_stock.a_stock_data.sectors import industry_fund_flow
        d = industry_fund_flow(top_n=top)
        inflow = (d.get("inflow_top") or [])[:top]
        outflow = (d.get("outflow_top") or [])[:top]
        if not inflow and not outflow:
            return ""
        fmt = lambda items: " ".join(f"{x['name']}{x['net_flow_yi']:+.0f}亿" for x in items)
        line = "\n**板块资金流(今日)**\n"
        if outflow:
            line += f"- 🔴流出: {fmt(outflow)}\n"
        if inflow:
            line += f"- 🟢流入: {fmt(inflow)}\n"
        return line
    except Exception:
        return ""


def main():
    sess = trading_session()
    if not sess["can_trade"]:
        print(f"🌙 休市 ({sess['session']}), 下个交易日开盘前再启心跳。")
        return

    prev = {}
    if STATE_FILE.exists():
        try:
            prev = json.loads(STATE_FILE.read_text())
        except Exception:
            prev = {}

    positions = _load_positions()
    mon = _parse_monitor(_run("a_stock.monitor", "--dry-run"))
    risk = _parse_risk(_run("a_stock.risk_metrics"))
    off = _parse_offensive(_run("a_stock.edge_scanner", "--top", "12"))

    now = datetime.now().strftime("%H:%M")
    day_pct = mon.get("day_pct")
    pnl = risk.get("pnl")
    heat = risk.get("heat_pct")
    p_day = prev.get("day_pct")
    p_pnl = prev.get("pnl")

    def _trend(a, b, fmt="{:.2f}"):
        if a is None or b is None:
            return "—"
        return _arrow(a - b, fmt)

    def _pct(px, prev_px):
        if not prev_px or prev_px <= 0:
            return "—"
        return _arrow((px - prev_px) / prev_px * 100, "{:.2f}%")

    prev_prices = prev.get("prices", {})
    prev_cands = set(prev.get("candidates", []))
    cur_codes = [r["code"] for r in off]
    new_n = len([c for c in cur_codes if c not in prev_cands])

    # ---- 组合 (单行表) ----
    day_s = f"{day_pct:+.2f}%" if day_pct is not None else "—"
    pnl_s = f"{pnl:+d}" if pnl is not None else "—"
    heat_s = f"{heat:.2f}%" if heat is not None else "—"
    out = [
        f"\n🫀 **心跳 {now}** | {sess['session']}\n",
        "\n| 时段 | 日内 | 5min | 浮盈 | 5min | Heat | 触发 | 异动 |\n",
        "|---|---|---|---|---|---|---|---|\n",
        f"| {sess['session']} | {day_s} | {_trend(day_pct, p_day)} | "
        f"{pnl_s}元 | {_trend(pnl, p_pnl, '{:.0f}')} | {heat_s} | "
        f"{mon.get('trig', 0)} | {mon.get('anom', 0)} |\n",
    ]
    out.append(_sector_flow())

    # ---- 持仓 ----
    out.append("\n| 代码 | 名称 | 现价 | 5min | 浮盈 |\n")
    out.append("|---|---|---|---|---|\n")
    for p in positions:
        px = p["price"]
        out.append(f"| {p['code']} | {p['name'][:6]} | {px:.3f} | "
                   f"{_pct(px, prev_prices.get(p['code']))} | {p.get('unrealized_pnl', 0):+.0f} |\n")

    # ---- 进攻 ----
    if off:
        out.append(f"\n**进攻** — {len(off)}只可操作({new_n}新) · 主推 `{off[0]['setup']}`\n\n")
        out.append("| 代码 | 名称 | 现价 | 止损 | 目标 | 股数 | 仓位 |\n")
        out.append("|---|---|---|---|---|---|---|\n")
        for r in off:
            out.append(f"| {r['code']} | {r['name'][:6]} | {r['entry']:.2f} | {r['stop']:.2f} | "
                       f"{r['target']:.2f} | {r['shares']} | {r['pct']:.0f}% |\n")
    else:
        out.append("\n**进攻**: 无候选 (无setup命中或净期望≤成本)\n")

    # ---- 写状态 ----
    state = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "day_pct": day_pct, "pnl": pnl, "heat_pct": heat,
        "prices": {p["code"]: p["price"] for p in positions},
        "candidates": cur_codes,
    }
    try:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False))
    except Exception:
        pass

    print("".join(out), end="")


if __name__ == "__main__":
    main()
