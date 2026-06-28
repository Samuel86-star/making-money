"""主监控循环: 拉行情 → 比对规则 → 异动检测 → 推送 + 写日志.
由 cron 每 5 分钟调用一次 (交易时段 9:30-11:30, 13:00-15:00)."""
import argparse
import json
import re
import sqlite3
import threading
import traceback
import urllib.request
from datetime import datetime, date, time as dtime, timedelta
from pathlib import Path
import yaml

import a_stock.config as cfg
from a_stock.notifier import push

STATE_FILE = cfg.DATA_DIR / "monitor_state.json"
RULES_FILE = Path(__file__).parent / "rules.yaml"
MONITOR_ERROR_LOG = cfg.DATA_DIR / "monitor_errors.jsonl"

CANDIDATE_CODES = ["515650", "600276", "300059", "159801", "159915", "515880"]

# 非阻塞锁防重入 (抄 aiagents-stock sector_strategy_scheduler.py:98-108)
# LLM/异动分析易超时, 下个时间点到了上一个没完, blocking=False 直接跳过
_run_lock = threading.Lock()


def _log_error(module: str, func: str, exc: Exception) -> None:
    """追加结构化错误日志到 monitor_errors.jsonl + push 通知."""
    record = {
        "ts": datetime.now().isoformat(),
        "module": module,
        "function": func,
        "error": str(exc),
        "traceback": traceback.format_exc(),
    }
    try:
        with open(str(MONITOR_ERROR_LOG), "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 日志写入失败不再递归报错
    # 严重错误推送到桌面
    push("⚠ monitor异常", f"[{module}] {func}: {str(exc)[:120]}", sound=True)


def _live_prices(codes: list[str]) -> dict[str, dict]:
    """批量拉 qt.gtimg.cn 实时报价."""
    out = {}
    prefix_map = lambda c: "sh" if c.startswith(("5", "6", "9")) else "sz"
    qs = ",".join(f"{prefix_map(c)}{c}" for c in codes)
    url = f"http://qt.gtimg.cn/q={qs}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = r.read().decode("gbk", errors="ignore")
    except Exception as e:
        print(f"⚠ 拉价失败: {e}")
        return out

    for line in data.strip().split("\n"):
        m = re.match(r'v_([a-z]+)(\d+)="([^"]+)"', line)
        if not m:
            continue
        code, payload = m.group(2), m.group(3)
        if code not in codes:
            continue
        parts = payload.split("~")
        if len(parts) < 50:
            continue
        try:
            prev_close = float(parts[4]) if parts[4] else 0
            price = float(parts[3]) if parts[3] else 0
            out[code] = {
                "name": parts[1],
                "price": price,
                "prev_close": prev_close,
                "open": float(parts[5]) if parts[5] else 0,
                "volume": int(parts[6]) if parts[6] else 0,
                "change_pct": (price - prev_close) / prev_close * 100 if prev_close else 0,
                "high": float(parts[33]) if len(parts) > 33 and parts[33] else 0,
                "low": float(parts[34]) if len(parts) > 34 and parts[34] else 0,
            }
        except (ValueError, IndexError):
            continue
    return out


def _load_holdings() -> list[dict]:
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT code, name, price, quantity, plan_stop_loss
        FROM decisions
        WHERE action IN ('buy','add') AND close_date IS NULL
    """).fetchall()
    conn.close()
    agg = {}
    for r in rows:
        c = r["code"]
        if c not in agg:
            agg[c] = {"code": c, "name": r["name"] or c, "qty": 0,
                      "cost": 0.0, "stop_loss": r["plan_stop_loss"]}
        a = agg[c]
        a["cost"] = (a["cost"] * a["qty"] + r["price"] * r["quantity"]) / (a["qty"] + r["quantity"])
        a["qty"] += r["quantity"]
        # 后加仓如果更新了止损, 取最新
        if r["plan_stop_loss"] is not None:
            a["stop_loss"] = r["plan_stop_loss"]
    return list(agg.values())


def _load_rules() -> list[dict]:
    if not RULES_FILE.exists():
        return []
    return yaml.safe_load(RULES_FILE.read_text()).get("rules", [])


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"triggers": {}, "last_run": None}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def _check_cooldown(state: dict, rule_name: str, max_per_day: int, cooldown_min: int) -> bool:
    today = str(date.today())
    triggers = state["triggers"].get(rule_name, [])
    today_triggers = [t for t in triggers if t["date"] == today]
    if len(today_triggers) >= max_per_day:
        return False
    if today_triggers and cooldown_min:
        last = today_triggers[-1]
        last_dt = datetime.fromisoformat(last["ts"])
        if datetime.now() - last_dt < timedelta(minutes=cooldown_min):
            return False
    return True


def _record_trigger(state: dict, rule_name: str, code: str, payload: dict) -> None:
    state["triggers"].setdefault(rule_name, []).append({
        "date": str(date.today()),
        "ts": datetime.now().isoformat(),
        "code": code,
        "payload": payload,
    })
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    state["triggers"][rule_name] = [
        t for t in state["triggers"][rule_name] if t["date"] >= cutoff
    ]


def _eval_condition(cond: dict, price: float, change_pct: float) -> bool:
    field = cond.get("field", "price")
    op = cond.get("op", "<=")
    val = cond.get("value", 0)
    actual = {"price": price, "change_pct": change_pct}.get(field)
    if actual is None:
        return False
    if op == "<=":
        return actual <= val
    if op == ">=":
        return actual >= val
    if op == "between":
        lo, hi = val
        return lo <= actual <= hi
    if op == "<":
        return actual < val
    if op == ">":
        return actual > val
    return False


def _check_extra(rule: dict) -> bool:
    extra = rule.get("extra", {})
    if not extra:
        return True
    now = datetime.now()
    if "weekday_min" in extra and now.weekday() < extra["weekday_min"]:
        return False
    if "weekday_max" in extra and now.weekday() > extra["weekday_max"]:
        return False
    if "time_after" in extra:
        h, m = map(int, extra["time_after"].split(":"))
        if now.time() < dtime(h, m):
            return False
    if "time_before" in extra:
        h, m = map(int, extra["time_before"].split(":"))
        if now.time() > dtime(h, m):
            return False
    return True


def _ensure_monitor_log_table() -> None:
    with sqlite3.connect(str(cfg.DECISIONS_DB)) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""
            CREATE TABLE IF NOT EXISTS monitor_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                rule TEXT NOT NULL,
                code TEXT,
                payload TEXT,
                body TEXT
            )
        """)


def run(dry_run: bool = False) -> dict:
    # 非阻塞锁: 上一次没跑完就跳过 (防任务堆积)
    if not _run_lock.acquire(blocking=False):
        return {"fired": 0, "rules_checked": 0, "error": "skipped_previous_running"}
    try:
        return _run_impl(dry_run)
    finally:
        _run_lock.release()


def _run_impl(dry_run: bool) -> dict:
    try:
        _ensure_monitor_log_table()
        state = _load_state()
        rules = _load_rules()
        holdings = _load_holdings()
        codes = list({h["code"] for h in holdings} | set(CANDIDATE_CODES))
        prices = _live_prices(codes)
        if not prices:
            return {"fired": 0, "rules_checked": 0, "error": "no_prices"}

        port_value, port_prev = 0, 0
        for h in holdings:
            if h["code"] in prices:
                p = prices[h["code"]]
                port_value += p["price"] * h["qty"]
                port_prev += p["prev_close"] * h["qty"]
        portfolio_change = (port_value - port_prev) / port_prev * 100 if port_prev else 0

        fired = []
        for rule in rules:
            if not rule.get("active", True):
                continue
            if not _check_extra(rule):
                continue

            if rule.get("applies_to") == "all_holdings":
                for h in holdings:
                    if h["code"] not in prices:
                        continue
                    p = prices[h["code"]]
                    if _eval_condition(rule["condition"], p["price"], p["change_pct"]):
                        key = f"{rule['name']}({h['code']})"
                        if _check_cooldown(state, key, rule.get("max_trigger_per_day", 1),
                                           rule.get("cooldown_min", 0)):
                            fired.append((rule, h["code"], p))
                            _record_trigger(state, key, h["code"],
                                            {"price": p["price"], "change_pct": p["change_pct"]})
            else:
                code = rule.get("code")
                cond = rule.get("condition", {})
                if not code or code not in prices:
                    continue
                p = prices[code]
                field = cond.get("field", "price")
                if field == "portfolio_change_pct":
                    val = portfolio_change
                    if _eval_condition(cond, 0, val):
                        if _check_cooldown(state, rule["name"],
                                           rule.get("max_trigger_per_day", 1),
                                           rule.get("cooldown_min", 0)):
                            fired.append((rule, "PORTFOLIO", {"portfolio_change_pct": val}))
                            _record_trigger(state, rule["name"], "PORTFOLIO",
                                            {"portfolio_change_pct": val})
                    continue
                if _eval_condition(cond, p["price"], p["change_pct"]):
                    if _check_cooldown(state, rule["name"],
                                       rule.get("max_trigger_per_day", 1),
                                       rule.get("cooldown_min", 0)):
                        fired.append((rule, code, p))
                        _record_trigger(state, rule["name"], code,
                                        {"price": p["price"], "change_pct": p["change_pct"]})

        for rule, code, p in fired:
            action_emoji = {"add": "🟢", "reduce": "🟡", "close": "🔴", "info": "🔔"}.get(rule.get("action"), "🔔")
            title = f"{action_emoji} {rule['action'].upper()}: {p.get('name', code) or code}"
            if rule.get("note"):
                title = f"{action_emoji} {p.get('name', code) or code} - {rule['note'][:25]}"
            body_parts = []
            if "price" in p:
                body_parts.append(f"价格 {p['price']:.3f}")
            if "change_pct" in p:
                body_parts.append(f"涨跌 {p['change_pct']:+.2f}%")
            if "portfolio_change_pct" in p:
                body_parts.append(f"组合 {p['portfolio_change_pct']:+.2f}%")
            if rule.get("shares"):
                body_parts.append(f"建议{rule['action']} {rule['shares']}股")
            body = " | ".join(body_parts)

            is_urgent = "紧急" in rule.get("name", "") or rule.get("action") == "info"
            if not dry_run:
                push(title, body, sound=is_urgent)
                with sqlite3.connect(str(cfg.DECISIONS_DB)) as c:
                    c.execute("""
                        INSERT INTO monitor_log (ts, rule, code, payload, body)
                        VALUES (?, ?, ?, ?, ?)
                    """, (datetime.now().isoformat(), rule["name"], code,
                          json.dumps(p, ensure_ascii=False, default=str), body))
            print(f"🔔 {title} | {body}")

        # === 异动检测 ===
        anomaly_fired = _check_anomalies(holdings, state, dry_run)

        state["last_run"] = datetime.now().isoformat()
        _save_state(state)

        return {"fired": len(fired), "rules_checked": len(rules),
                "holdings": len(holdings),
                "anomaly_fired": anomaly_fired,
                "portfolio_change": round(portfolio_change, 2)}
    except Exception as e:
        _log_error("monitor", "_run_impl", e)
        return {"fired": 0, "rules_checked": 0, "error": str(e)}


def _check_anomalies(holdings: list[dict], state: dict, dry_run: bool) -> int:
    """异动检测: 火箭发射/高台跳水. 每标的一天最多推2次."""
    try:
        from a_stock.anomaly import check as anomaly_check, _is_trading_time
        if not _is_trading_time():
            return 0

        fired = 0
        # 持仓 + watchlist
        from a_stock.anomaly_holdings_loader import load_targets
        targets = load_targets()

        for t in targets:
            code = t["code"]
            key = f"anomaly({code})"
            # 一天最多2次异动推送
            if not _check_cooldown(state, key, max_per_day=2, cooldown_min=15):
                continue
            try:
                sig = anomaly_check(code, t.get("name", ""))
            except Exception as e:
                print(f"⚠ 异动检测 {code} 失败: {e}")
                continue
            if not sig:
                continue

            title = f"{sig['type']}: {sig['name']}"
            body = (f"价格 {sig['price']:.3f} | 3分钟涨速 {sig['speed_3min']:+.2f}% | "
                    f"量比 {sig['vol_ratio']:.1f} | {sig['trend']}")
            is_urgent = "跳水" in sig["type"]
            if not dry_run:
                push(title, body, sound=is_urgent)
                with sqlite3.connect(str(cfg.DECISIONS_DB)) as c:
                    c.execute("""
                        INSERT INTO monitor_log (ts, rule, code, payload, body)
                        VALUES (?, ?, ?, ?, ?)
                    """, (datetime.now().isoformat(), sig["type"], code,
                          json.dumps(sig, ensure_ascii=False, default=str), body))
            _record_trigger(state, key, code,
                            {"speed": sig["speed_3min"], "vol_ratio": sig["vol_ratio"]})
            print(f"🚨 {title} | {body}")
            fired += 1
        return fired
    except Exception as e:
        _log_error("monitor", "_check_anomalies", e)
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    result = run(args.dry_run)
    print(f"\n检查 {result.get('rules_checked', 0)} 规则, "
          f"持仓 {result.get('holdings', 0)} 只, "
          f"组合日内 {result.get('portfolio_change', 0):+.2f}%, "
          f"规则触发 {result['fired']} 条, "
          f"异动触发 {result.get('anomaly_fired', 0)} 条")


if __name__ == "__main__":
    main()
