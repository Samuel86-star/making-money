"""机会流聚合: 4类机会(回踩买点/异动/候选/规则)实时算, 返回统一结构.

纯函数, 数据获取与渲染分离. 各 _xxx_signals 函数可独立 mock 测."""
import sqlite3
from datetime import datetime
import a_stock.config as cfg


def _watched_codes() -> list[str]:
    """持仓 + watchlist 代码 (回踩买点扫描范围)."""
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT DISTINCT code FROM decisions
        WHERE action IN ('buy','add') AND close_date IS NULL
        UNION
        SELECT code FROM watchlist
    """).fetchall()
    conn.close()
    return [r["code"] for r in rows]


_FALLBACK_NAMES = {
    "515650": "消费50ETF富国", "159801": "芯片ETF广发",
    "159915": "创业板ETF易方达", "159516": "半导体材料设备ETF",
    "600276": "恒瑞医药", "300059": "东方财富",
    "515880": "通信ETF国泰",
}


def _resolve_name(code: str, name: str = "") -> str:
    """标的名称回退: 调用方传入的name → watchlist.name → 内置FALLBACK → ''."""
    if name:
        return name
    try:
        conn = sqlite3.connect(str(cfg.DECISIONS_DB))
        row = conn.execute("SELECT name FROM watchlist WHERE code=?", (code,)).fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
    except Exception:
        pass
    return _FALLBACK_NAMES.get(code, "")


def _holding_cost(code: str) -> float | None:
    """某标的真实成本 (移动加权, lot制剩余). 无持仓返回 None.

    NOTE: 成本lot逻辑与 a_stock/risk_metrics._load_positions 重复 (06-29教训fix),
    后续可抽到 db.py 共享. 当前两处各自维护."""
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    conn.row_factory = sqlite3.Row
    lots = conn.execute(
        "SELECT id, price, quantity FROM decisions WHERE code=? AND action IN('buy','add') AND close_date IS NULL",
        (code,)).fetchall()
    reduces = conn.execute(
        "SELECT parent_id, SUM(quantity) AS qty FROM decisions WHERE code=? AND action='reduce' AND close_date IS NOT NULL GROUP BY parent_id",
        (code,)).fetchall()
    conn.close()
    red = {r["parent_id"]: r["qty"] for r in reduces}
    qty_sum = cost_sum = 0.0
    for lot in lots:
        remaining = lot["quantity"] - red.get(lot["id"], 0)
        if remaining > 0:
            qty_sum += remaining
            cost_sum += lot["price"] * remaining
    return cost_sum / qty_sum if qty_sum else None


def _pullback_signals() -> list[dict]:
    """回踩买点: 多头排列+回踩MA5/MA10不破."""
    from a_stock.scorers.technical_scorer import score
    from a_stock.risk_metrics import _live_price
    import logging
    out = []
    for code in _watched_codes():
        try:
            fs = score(code)
        except Exception as e:
            logging.getLogger("a_stock.web").warning("pullback score %s failed: %s", code, e)
            continue
        pb = fs.detail.get("pullback_buy") if fs and fs.detail else None
        if not pb:
            continue
        px = _live_price(code) or 0.0
        out.append({
            "code": code, "name": _resolve_name(code), "ma": pb,
            "price": px, "cost": _holding_cost(code) or 0.0,
        })
    return out


def _anomaly_signals() -> list[dict]:
    """异动: anomaly.scan_holdings."""
    try:
        from a_stock.anomaly import scan_holdings
        sigs = scan_holdings()
    except Exception:
        return []
    out = []
    for s in sigs:
        out.append({
            "code": s.get("code", ""), "name": s.get("name", ""),
            "desc": f"{s.get('type','') or ''} 涨速{s.get('speed_3min') or 0}% 量比{s.get('vol_ratio') or 0}",
            "change": s.get("speed_3min") or 0,
        })
    return out


def _candidate_signals() -> list[dict]:
    """早盘候选: 读 candidate_history 最近一次扫描 top5."""
    try:
        conn = sqlite3.connect(str(cfg.SCREENER_DB))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT code, name, score, sector FROM candidate_history
            WHERE scan_date = (SELECT MAX(scan_date) FROM candidate_history)
            ORDER BY score DESC LIMIT 5
        """).fetchall()
        conn.close()
    except Exception:
        return []
    return [{"code": r["code"], "name": r["name"] or "",
             "score": r["score"] or 0, "desc": f"{r['sector'] or ''} 候选"} for r in rows]


def _rule_signals() -> list[dict]:
    """规则触发+watchlist回踩提醒: 读 rules.yaml + monitor_log."""
    import yaml
    from a_stock.risk_metrics import _live_price
    rules_file = cfg.ROOT / "a_stock" / "rules.yaml"
    if not rules_file.exists():
        return []
    try:
        rules = yaml.safe_load(rules_file.read_text()).get("rules", [])
    except yaml.YAMLError:
        return []
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    conn.row_factory = sqlite3.Row
    fired = conn.execute(
        "SELECT rule, code FROM monitor_log WHERE date(ts)=date('now')").fetchall()
    conn.close()
    fired_keys = {(r["rule"], r["code"]) for r in fired}
    out = []
    for rule in rules:
        if not rule.get("active", True):
            continue
        code = rule.get("code")
        if not code:
            continue
        is_fired = (rule["name"], code) in fired_keys
        current_px = _live_price(code) or 0.0
        out.append({
            "code": code, "name": _resolve_name(code), "desc": rule.get("note", ""),
            "trigger_price": rule.get("condition", {}).get("value"),
            "current": current_px, "fired": is_fired,
        })
    return out


def collect_opportunities() -> list[dict]:
    """聚合4类机会, 返回统一结构."""
    opps = []
    for s in _pullback_signals():
        opps.append({
            "type": "pullback", "time": datetime.now().strftime("%H:%M"),
            "code": s["code"], "name": s["name"] or s["code"],
            "desc": f"多头排列 + {s['ma']}不破 → 加仓信号",
            "meta": f"现{s['price']:.3f} · 成本{s['cost']:.3f}",
            "tag": "📍 回踩买点", "action_label": "加仓",
        })
    for s in _anomaly_signals():
        opps.append({
            "type": "anomaly", "time": datetime.now().strftime("%H:%M"),
            "code": s["code"], "name": s["name"],
            "desc": s["desc"], "meta": "",
            "tag": "⚡ 异动", "action_label": f"+{s['change']:.1f}%",
        })
    for s in _candidate_signals():
        opps.append({
            "type": "candidate", "time": "09:35",
            "code": s["code"], "name": s["name"],
            "desc": s["desc"], "meta": f"评分 {s['score']:.1f}",
            "tag": "🎯 早盘候选", "action_label": f"{s['score']:.0f}分",
        })
    for s in _rule_signals():
        opps.append({
            "type": "rule", "time": "已触" if s["fired"] else "待触",
            "code": s["code"], "name": s["name"] or s["code"],
            "desc": s["desc"],
            "meta": f"触发价{s['trigger_price']} · 现{s['current']:.3f}",
            "tag": "🔔 规则" + ("触发" if s["fired"] else "待触"),
            "action_label": None if not s["fired"] else "已触",
        })
    return opps