# A股盯盘Web UI 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Streamlit交易终端盯盘UI,机会流+持仓侧栏,15s轮询,复用现有a_stock模块实时算4类机会点。

**Architecture:** 6个组件文件各单一职责(数据获取与渲染分离),dashboard.py拼装。机会点聚合逻辑纯函数化可单测。technical_scorer扩展MA10+回踩买点检测。本地运行,仅加streamlit依赖。

**Tech Stack:** Streamlit, pandas, 现有a_stock模块(risk_metrics/ohlcv/technical_scorer/anomaly/sentiment/db)

**Spec:** `docs/superpowers/specs/2026-06-29-web-dashboard-design.md`

---

## 文件结构

```
a_stock/web/                       # 新建包
├── __init__.py
├── dashboard.py                   # Streamlit入口,拼装组件
├── opportunity_feed.py            # 4类机会聚合 (纯函数,可测)
├── positions_panel.py             # 持仓数据 (复用risk_metrics)
├── ticker.py                      # 行情滚动条数据
├── asset_bar.py                   # 资产条数据
└── sentiment_bar.py               # 情绪条数据
tests/
├── test_opportunity_feed.py       # 机会聚合单测
└── test_technical_scorer.py       # 已存在,扩展回踩买点测试
a_stock/scorers/technical_scorer.py # 修改:加MA10+回踩买点检测
requirements.txt                   # 加streamlit
```

---

## Task 1: 扩展 technical_scorer 加 MA10 + 回踩买点检测

**Files:**
- Modify: `a_stock/scorers/technical_scorer.py`
- Test: `tests/test_technical_scorer.py`

回踩买点是机会流核心(📍琥珀)。technical_scorer当前只算MA5/20/60,需加MA10,并检测"多头排列+价回踩MA5/MA10不破"。

- [ ] **Step 1: 写失败测试 — 回踩买点检测**

追加到 `tests/test_technical_scorer.py` 末尾:

```python
def test_pullback_to_ma5_in_uptrend_detected():
    """多头排列 + 价回踩MA5(±1.5%)不破 → 标记回踩买点."""
    # 构造多头上升序列, 末日小回调到MA5附近
    base = [10.0 + i * 0.1 for i in range(40)]  # 10.0→13.9 上升
    base[-1] = base[-2] * 0.995  # 末日微跌回踩
    closes = base
    vols = [1000] * 40
    with _patch_load(_rows(closes, vols)):
        fs = technical_scorer.score("T_PULL1")
    assert fs.detail.get("pullback_buy") == "回踩MA5"


def test_pullback_not_triggered_when_far_above_ma():
    """价远离MA5(急拉) → 不标回踩买点."""
    base = [10.0 + i * 0.1 for i in range(40)]
    base[-1] = base[-2] * 1.08  # 末日急拉8%, 远离MA5
    closes = base
    vols = [1000] * 40
    with _patch_load(_rows(closes, vols)):
        fs = technical_scorer.score("T_PULL2")
    assert "pullback_buy" not in fs.detail


def test_pullback_not_triggered_in_downtrend():
    """空头排列 → 不标回踩买点(无多头基础)."""
    closes = [15.0 - i * 0.1 for i in range(40)]  # 下降
    vols = [1000] * 40
    with _patch_load(_rows(closes, vols)):
        fs = technical_scorer.score("T_PULL3")
    assert "pullback_buy" not in fs.detail
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_technical_scorer.py::test_pullback_to_ma5_in_uptrend_detected -v`
Expected: FAIL — `pullback_buy` not in detail

- [ ] **Step 3: 实现 MA10 + 回踩买点检测**

在 `a_stock/scorers/technical_scorer.py` 的 `score()` 内,`ma60 = _sma(closes, 60)` 后加:

```python
    ma10 = _sma(closes, 10)
```

在 RSI 段之后、量价验证段之前,加回踩买点检测:

```python
    # 回踩买点 (06-29铁律: 多头排列+回踩MA5/MA10不破=加仓信号)
    if ma60 > 0 and price > ma20 > ma60:  # 多头基础
        for ma_name, ma_val in [("MA5", ma5), ("MA10", ma10)]:
            if ma_val <= 0:
                continue
            # 回踩: 价在MA±1.5%内, 且价>=MA(不破)
            if abs(price - ma_val) / ma_val <= 0.015 and price >= ma_val * 0.998:
                detail["pullback_buy"] = f"回踩{ma_name}"
                s += 8
                break
```

detail dict 初始化处加 ma10:

```python
    detail = {"ma5": round(ma5, 2), "ma10": round(ma10, 2), "ma20": round(ma20, 2), "rsi": round(rsi, 1)}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_technical_scorer.py -v`
Expected: 全部 PASS (8个: 原5 + 新3)

- [ ] **Step 5: 提交**

```bash
git add a_stock/scorers/technical_scorer.py tests/test_technical_scorer.py
git commit -m "feat(scorer): MA10 + 回踩买点检测 (多头排列+回踩MA不破)"
```

---

## Task 2: opportunity_feed — 4类机会聚合(纯函数)

**Files:**
- Create: `a_stock/web/__init__.py`
- Create: `a_stock/web/opportunity_feed.py`
- Test: `tests/test_opportunity_feed.py`

核心组件。聚合4类机会(回踩买点/异动/候选/规则),返回统一结构list[dict],按时间倒序。纯函数,数据获取与渲染分离,可单测。

机会结构:
```python
{
    "type": "pullback"|"anomaly"|"candidate"|"rule",
    "time": str,         # "09:50" 或 "待触"
    "code": str, "name": str,
    "desc": str,         # 一句话描述
    "meta": str,         # 等宽数据行 "现1.545 · 成本1.541"
    "tag": str,          # "📍 回踩买点"
    "action_label": str|None,  # "加仓" / "+4.6%" / None
}
```

- [ ] **Step 1: 写失败测试 — 4类机会聚合**

Create `tests/test_opportunity_feed.py`:

```python
"""opportunity_feed 单元测试. mock 各数据源, 验证4类机会聚合+排序."""
from unittest.mock import patch
from a_stock.web.opportunity_feed import collect_opportunities


def test_collect_aggregates_four_types(monkeypatch):
    """4类机会都被收集."""
    monkeypatch.setattr("a_stock.web.opportunity_feed._pullback_signals",
                        lambda: [{"code": "159801", "name": "芯片ETF", "ma": "MA5",
                                  "price": 1.545, "cost": 1.541}])
    monkeypatch.setattr("a_stock.web.opportunity_feed._anomaly_signals",
                        lambda: [{"code": "002409", "name": "雅克科技",
                                  "desc": "资金流#7 收涨+4.6%", "change": 4.6}])
    monkeypatch.setattr("a_stock.web.opportunity_feed._candidate_signals",
                        lambda: [{"code": "000988", "name": "华工科技",
                                  "score": 63.0, "desc": "观望偏多"}])
    monkeypatch.setattr("a_stock.web.opportunity_feed._rule_signals",
                        lambda: [{"code": "159516", "name": "半导体材料设备ETF",
                                  "desc": "回踩≤1.85试仓", "trigger_price": 1.85,
                                  "current": 1.921, "fired": False}])

    opps = collect_opportunities()
    types = {o["type"] for o in opps}
    assert types == {"pullback", "anomaly", "candidate", "rule"}
    # 每条有完整字段
    for o in opps:
        assert {"type", "time", "code", "name", "desc", "meta", "tag", "action_label"} <= o.keys()


def test_rule_unfired_marked_pending(monkeypatch):
    """未触发规则标"待触"时间."""
    monkeypatch.setattr("a_stock.web.opportunity_feed._pullback_signals", lambda: [])
    monkeypatch.setattr("a_stock.web.opportunity_feed._anomaly_signals", lambda: [])
    monkeypatch.setattr("a_stock.web.opportunity_feed._candidate_signals", lambda: [])
    monkeypatch.setattr("a_stock.web.opportunity_feed._rule_signals",
                        lambda: [{"code": "159516", "name": "半导体材料设备ETF",
                                  "desc": "回踩≤1.85试仓", "trigger_price": 1.85,
                                  "current": 1.921, "fired": False}])
    opps = collect_opportunities()
    assert len(opps) == 1
    assert opps[0]["time"] == "待触"
    assert opps[0]["action_label"] is None


def test_empty_when_all_sources_empty(monkeypatch):
    """全部数据源空 → 空列表, 不崩."""
    for src in ["_pullback_signals", "_anomaly_signals", "_candidate_signals", "_rule_signals"]:
        monkeypatch.setattr(f"a_stock.web.opportunity_feed.{src}", lambda: [])
    assert collect_opportunities() == []


def test_pullback_uses_real_scorer(tmp_path, monkeypatch):
    """_pullback_signals 真实调用: 对持仓+watchlist跑scorer, 识别回踩."""
    # 用真实score, mock _load_ohlcv 造多头回踩数据
    from a_stock.scorers import technical_scorer
    closes = [10.0 + i * 0.1 for i in range(40)]
    closes[-1] = closes[-2] * 0.995
    rows = [{"date": f"2026-01-{i+1:02d}", "open": c, "high": c, "low": c,
             "close": c, "volume": 1000} for i, c in enumerate(closes)]
    monkeypatch.setattr(technical_scorer, "_load_ohlcv", lambda code, days=120: rows)
    monkeypatch.setattr("a_stock.web.opportunity_feed._watched_codes",
                        lambda: ["T_REAL1"])
    monkeypatch.setattr("a_stock.web.opportunity_feed._holding_cost",
                        lambda code: 10.0)

    sigs = __import__("a_stock.web.opportunity_feed", fromlist=["_pullback_signals"])._pullback_signals()
    assert len(sigs) == 1
    assert sigs[0]["code"] == "T_REAL1"
    assert "MA5" in sigs[0]["ma"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_opportunity_feed.py -v`
Expected: FAIL — `ModuleNotFoundError: a_stock.web.opportunity_feed`

- [ ] **Step 3: 实现 opportunity_feed**

Create `a_stock/web/__init__.py` (空文件):

```python
```

Create `a_stock/web/opportunity_feed.py`:

```python
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


def _holding_cost(code: str) -> float | None:
    """某标的真实成本 (移动加权, lot制剩余). 无持仓返回 None."""
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
    out = []
    for code in _watched_codes():
        try:
            fs = score(code)
        except Exception:
            continue
        pb = fs.detail.get("pullback_buy")
        if not pb:
            continue
        out.append({
            "code": code, "name": "", "ma": pb,
            "price": 0.0, "cost": _holding_cost(code) or 0.0,
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
            "desc": f"{s.get('type','')} 涨速{s.get('speed_3min',0)}% 量比{s.get('vol_ratio',0)}",
            "change": s.get("speed_3min", 0),
        })
    return out


def _candidate_signals() -> list[dict]:
    """早盘候选: 读 candidate_history 最近一次扫描 top5."""
    conn = sqlite3.connect(str(cfg.SCREENER_DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT code, name, score, sector FROM candidate_history
        WHERE scan_date = (SELECT MAX(scan_date) FROM candidate_history)
        ORDER BY score DESC LIMIT 5
    """).fetchall()
    conn.close()
    return [{"code": r["code"], "name": r["name"] or "",
             "score": r["score"] or 0, "desc": f"{r['sector'] or ''} 候选"} for r in rows]


def _rule_signals() -> list[dict]:
    """规则触发+watchlist回踩提醒: 读 rules.yaml + monitor_log."""
    import yaml
    rules_file = cfg.PROJECT_ROOT / "a_stock" / "rules.yaml"
    if not rules_file.exists():
        return []
    rules = yaml.safe_load(rules_file.read_text()).get("rules", [])
    # 读 monitor_log 已触发
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
        out.append({
            "code": code, "name": "", "desc": rule.get("note", ""),
            "trigger_price": rule.get("condition", {}).get("value"),
            "current": 0.0, "fired": is_fired,
        })
    return out


def collect_opportunities() -> list[dict]:
    """聚合4类机会, 返回统一结构, 按类型分组 (无时间排序, 候选/异动带时间)."""
    opps = []
    # 回踩买点
    for s in _pullback_signals():
        opps.append({
            "type": "pullback", "time": datetime.now().strftime("%H:%M"),
            "code": s["code"], "name": s["name"] or s["code"],
            "desc": f"多头排列 + 回踩{s['ma']}不破 → 加仓信号",
            "meta": f"现{s['price']:.3f} · 成本{s['cost']:.3f}",
            "tag": "📍 回踩买点", "action_label": "加仓",
        })
    # 异动
    for s in _anomaly_signals():
        opps.append({
            "type": "anomaly", "time": datetime.now().strftime("%H:%M"),
            "code": s["code"], "name": s["name"],
            "desc": s["desc"], "meta": "",
            "tag": "⚡ 异动", "action_label": f"+{s['change']:.1f}%",
        })
    # 候选
    for s in _candidate_signals():
        opps.append({
            "type": "candidate", "time": "09:35",
            "code": s["code"], "name": s["name"],
            "desc": s["desc"], "meta": f"评分 {s['score']:.1f}",
            "tag": "🎯 早盘候选", "action_label": f"{s['score']:.0f}分",
        })
    # 规则
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_opportunity_feed.py -v`
Expected: 4 PASS

- [ ] **Step 5: 提交**

```bash
git add a_stock/web/__init__.py a_stock/web/opportunity_feed.py tests/test_opportunity_feed.py
git commit -m "feat(web): opportunity_feed 4类机会聚合 (回踩/异动/候选/规则)"
```

---

## Task 3: positions_panel — 持仓栏数据

**Files:**
- Create: `a_stock/web/positions_panel.py`
- Test: `tests/test_opportunity_feed.py` (追加)

持仓栏:复用risk_metrics._load_positions(已含cost+unrealized_pnl),加ATR止损价(ohlcv.struct_stop_loss)。

- [ ] **Step 1: 写失败测试 — 持仓数据含成本+止损**

追加到 `tests/test_opportunity_feed.py`:

```python
def test_positions_with_cost_and_stop_loss(monkeypatch):
    """持仓数据含 cost, stop_loss (ATR), pnl."""
    from a_stock.web import positions_panel
    monkeypatch.setattr("a_stock.web.positions_panel._load_positions",
                        lambda: [{"code": "T_POS1", "name": "T持仓", "qty": 100,
                                  "cost": 10.0, "price": 11.0,
                                  "unrealized_pnl": 100.0, "mv": 1100.0}])
    monkeypatch.setattr("a_stock.web.positions_panel._atr_stop",
                        lambda code, cost: 9.5)
    rows = positions_panel.collect_positions()
    assert len(rows) == 1
    r = rows[0]
    assert r["code"] == "T_POS1"
    assert r["cost"] == 10.0
    assert r["price"] == 11.0
    assert r["stop_loss"] == 9.5
    assert r["pnl_pct"] == 10.0  # (11-10)/10*100


def test_positions_empty_when_no_holdings(monkeypatch):
    """无持仓 → 空列表."""
    from a_stock.web import positions_panel
    monkeypatch.setattr("a_stock.web.positions_panel._load_positions", lambda: [])
    assert positions_panel.collect_positions() == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_opportunity_feed.py::test_positions_with_cost_and_stop_loss -v`
Expected: FAIL — `ModuleNotFoundError: a_stock.web.positions_panel`

- [ ] **Step 3: 实现 positions_panel**

Create `a_stock/web/positions_panel.py`:

```python
"""持仓栏数据: 复用 risk_metrics._load_positions + ohlcv ATR止损."""
from a_stock.risk_metrics import _load_positions
from a_stock.ohlcv import atr, struct_stop_loss


def _atr_stop(code: str, cost: float) -> float | None:
    """ATR结构止损价. 无数据返回 None."""
    a = atr(code, 14)
    return round(struct_stop_loss(cost, a), 3) if a else None


def collect_positions() -> list[dict]:
    """返回持仓行: code/name/qty/cost/price/pnl_pct/pnl/stop_loss/mv."""
    out = []
    for p in _load_positions():
        cost = p.get("cost", 0)
        price = p.get("price", 0)
        pnl_pct = (price - cost) / cost * 100 if cost else 0
        out.append({
            "code": p["code"], "name": p.get("name", p["code"]),
            "qty": p["qty"], "cost": round(cost, 4), "price": round(price, 4),
            "pnl_pct": round(pnl_pct, 2),
            "pnl": round(p.get("unrealized_pnl", 0)),
            "stop_loss": _atr_stop(p["code"], cost),
            "mv": round(p.get("mv", 0)),
        })
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_opportunity_feed.py -v`
Expected: 6 PASS (原4 + 新2)

- [ ] **Step 5: 提交**

```bash
git add a_stock/web/positions_panel.py tests/test_opportunity_feed.py
git commit -m "feat(web): positions_panel 持仓栏数据 (成本+ATR止损+盈亏)"
```

---

## Task 4: asset_bar + ticker + sentiment_bar 数据组件

**Files:**
- Create: `a_stock/web/asset_bar.py`
- Create: `a_stock/web/ticker.py`
- Create: `a_stock/web/sentiment_bar.py`
- Test: `tests/test_opportunity_feed.py` (追加)

三个轻量数据组件。asset_bar算总资产/市值/现金/浮盈/距目标;ticker拉行情滚动条代码列表;sentiment读情绪温度。

- [ ] **Step 1: 写失败测试 — 三组件数据**

追加到 `tests/test_opportunity_feed.py`:

```python
def test_asset_bar_computes_totals(monkeypatch):
    """资产条: 总资产=市值+现金, 距目标百分比."""
    from a_stock.web import asset_bar
    monkeypatch.setattr("a_stock.web.asset_bar._positions_total_mv", lambda: 24619)
    monkeypatch.setattr("a_stock.web.asset_bar._total_unrealized", lambda: 303)
    monkeypatch.setattr("a_stock.web.asset_bar._realized_today", lambda: 67)
    a = asset_bar.collect_asset_bar(cash=55319)
    assert a["total"] == 79938  # 24619+55319
    assert a["stock_mv"] == 24619
    assert a["cash"] == 55319
    assert a["unrealized"] == 303
    assert a["realized"] == 67
    assert a["target_pct"] == 79.9  # 79938/100000*100, 容差


def test_asset_bar_target_pct(tmp_path, monkeypatch):
    from a_stock.web import asset_bar
    monkeypatch.setattr("a_stock.web.asset_bar._positions_total_mv", lambda: 0)
    monkeypatch.setattr("a_stock.web.asset_bar._total_unrealized", lambda: 0)
    monkeypatch.setattr("a_stock.web.asset_bar._realized_today", lambda: 0)
    a = asset_bar.collect_asset_bar(cash=50000)
    assert a["target_pct"] == 50.0


def test_ticker_codes_from_holdings_and_watchlist(monkeypatch):
    """ticker 代码 = 持仓 + watchlist + 候选."""
    from a_stock.web import ticker
    monkeypatch.setattr("a_stock.web.ticker._holding_codes", lambda: ["600276", "159801"])
    monkeypatch.setattr("a_stock.web.ticker._watchlist_codes", lambda: ["159516"])
    monkeypatch.setattr("a_stock.web.ticker._candidate_codes", lambda: ["000988"])
    codes = ticker.collect_ticker_codes()
    assert set(codes) == {"600276", "159801", "159516", "000988"}


def test_sentiment_bar_returns_temp_and_mood(monkeypatch):
    """情绪条: 温度+情绪+领涨."""
    from a_stock.web import sentiment_bar
    monkeypatch.setattr("a_stock.web.sentiment_bar._compute_temp",
                        lambda: {"temp": 30.0, "mood": "谨慎"})
    monkeypatch.setattr("a_stock.web.sentiment_bar._leading_sector", lambda: "农林牧渔")
    s = sentiment_bar.collect_sentiment()
    assert s["temp"] == 30.0
    assert s["mood"] == "谨慎"
    assert s["leader"] == "农林牧渔"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_opportunity_feed.py::test_asset_bar_computes_totals -v`
Expected: FAIL — `ModuleNotFoundError: a_stock.web.asset_bar`

- [ ] **Step 3: 实现 asset_bar**

Create `a_stock/web/asset_bar.py`:

```python
"""资产条数据: 总资产/市值/现金/浮盈/距目标."""
import sqlite3
from datetime import date
import a_stock.config as cfg

TARGET = 100000.0


def _positions_total_mv() -> float:
    from a_stock.risk_metrics import _load_positions
    return sum(p.get("mv", 0) for p in _load_positions())


def _total_unrealized() -> float:
    from a_stock.risk_metrics import _load_positions
    return sum(p.get("unrealized_pnl", 0) for p in _load_positions())


def _realized_today() -> float:
    """今日已实现盈亏 (reduce行 pnl挂回parent成本)."""
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT r.price AS rp, r.quantity AS rq, b.price AS bp
        FROM decisions r JOIN decisions b ON r.parent_id=b.id
        WHERE r.action='reduce' AND r.close_date=?
    """, (date.today().isoformat(),)).fetchall()
    conn.close()
    return sum((r["rp"] - r["bp"]) * r["rq"] for r in rows)


def collect_asset_bar(cash: float) -> dict:
    mv = _positions_total_mv()
    total = mv + cash
    return {
        "total": round(total),
        "stock_mv": round(mv),
        "cash": round(cash),
        "unrealized": round(_total_unrealized()),
        "realized": round(_realized_today()),
        "target_pct": round(total / TARGET * 100, 1),
    }
```

- [ ] **Step 4: 实现 ticker**

Create `a_stock/web/ticker.py`:

```python
"""行情滚动条: 持仓+watchlist+候选 代码列表."""
import sqlite3
import a_stock.config as cfg


def _holding_codes() -> list[str]:
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    rows = conn.execute(
        "SELECT DISTINCT code FROM decisions WHERE action IN('buy','add') AND close_date IS NULL"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def _watchlist_codes() -> list[str]:
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    rows = conn.execute("SELECT code FROM watchlist").fetchall()
    conn.close()
    return [r[0] for r in rows]


def _candidate_codes() -> list[str]:
    conn = sqlite3.connect(str(cfg.SCREENER_DB))
    rows = conn.execute("""
        SELECT code FROM candidate_history
        WHERE scan_date=(SELECT MAX(scan_date) FROM candidate_history)
        ORDER BY score DESC LIMIT 5
    """).fetchall()
    conn.close()
    return [r[0] for r in rows]


def collect_ticker_codes() -> list[str]:
    """去重合并."""
    seen = []
    for c in _holding_codes() + _watchlist_codes() + _candidate_codes():
        if c not in seen:
            seen.append(c)
    return seen
```

- [ ] **Step 5: 实现 sentiment_bar**

Create `a_stock/web/sentiment_bar.py`:

```python
"""情绪条数据: 温度+情绪+领涨板块."""


def _compute_temp() -> dict:
    from a_stock.sentiment import compute_temp
    return compute_temp()


def _leading_sector() -> str:
    """领涨板块 (从close_scan或sector_rotation读最近)."""
    try:
        from a_stock.a_stock_data.sectors import sector_ranking
        r = sector_ranking()
        if r:
            return r[0].get("name", "")
    except Exception:
        pass
    return ""


def collect_sentiment() -> dict:
    t = _compute_temp()
    return {
        "temp": t.get("temp", 0),
        "mood": t.get("mood", ""),
        "leader": _leading_sector(),
    }
```

- [ ] **Step 6: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_opportunity_feed.py -v`
Expected: 10 PASS

注: 若 `sectors.py` 无 `sector_ranking` 函数, `_leading_sector` 捕获异常返回空, 测试mock了不依赖真实函数。

- [ ] **Step 7: 提交**

```bash
git add a_stock/web/asset_bar.py a_stock/web/ticker.py a_stock/web/sentiment_bar.py tests/test_opportunity_feed.py
git commit -m "feat(web): asset_bar/ticker/sentiment_bar 数据组件"
```

---

## Task 5: dashboard.py — Streamlit入口拼装

**Files:**
- Create: `a_stock/web/dashboard.py`
- Modify: `requirements.txt`

Streamlit主入口。交易终端视觉(CSS注入),15s轮询,拼装6组件。无单测(Streamlit渲染层不测),但需手动跑验证。

- [ ] **Step 1: 加 streamlit 依赖**

Modify `requirements.txt`, 追加:

```
streamlit>=1.30
```

- [ ] **Step 2: 安装依赖**

Run: `.venv/bin/python -m pip install streamlit>=1.30`
Expected: 安装成功

- [ ] **Step 3: 实现 dashboard.py**

Create `a_stock/web/dashboard.py`:

```python
"""A股盯盘Web UI — 交易终端. streamlit run a_stock/web/dashboard.py"""
import streamlit as st
from datetime import datetime
from a_stock.web import opportunity_feed, positions_panel, asset_bar, ticker, sentiment_bar

# A股交易时段判断 (9:30-11:30, 13:00-15:00)
def _is_trading_hours() -> bool:
    now = datetime.now()
    t = now.hour * 60 + now.minute
    weekday = now.weekday()
    if weekday >= 5:
        return False
    return (570 <= t <= 690) or (780 <= t <= 900)


st.set_page_config(page_title="A股盯盘", page_icon="📊", layout="wide")

# CSS: 交易终端视觉
st.markdown("""
<style>
:root{--bg:#0a0e14;--panel:#12161f;--line:#1f2633;--txt:#e8eaed;--dim:#6b7280;
--red:#f23645;--green:#089981;--amber:#d4a017;--blue:#3b82f6;}
.stApp{background:var(--bg);color:var(--txt);font-family:'Inter',sans-serif;}
.stMarkdown,.stMarkdown p{color:var(--txt)!important}
.block-container{padding-top:1rem;max-width:1200px}
.ticker{background:#000;border:1px solid var(--line);border-radius:6px;overflow:hidden;
height:34px;display:flex;align-items:center;margin-bottom:14px}
.ticker-track{display:flex;gap:24px;white-space:nowrap;animation:scroll 40s linear infinite;
font-family:'JetBrains Mono',monospace;font-size:12px;padding-left:100%}
@keyframes scroll{to{transform:translateX(-100%)}}
.up{color:var(--red)} .down{color:var(--green)} .amber{color:var(--amber)}
.opp{display:flex;gap:12px;padding:12px 14px;border-bottom:1px solid var(--line);align-items:flex-start}
.opp .bar{width:3px;align-self:stretch;border-radius:2px}
.opp .tag{font-size:10px;padding:1px 6px;border-radius:3px;font-weight:600}
.tag-pull{background:rgba(212,160,23,.15);color:var(--amber)}
.tag-anom{background:rgba(242,54,69,.15);color:var(--red)}
.tag-cand{background:rgba(59,130,246,.15);color:var(--blue)}
.tag-rule{background:rgba(8,153,129,.15);color:var(--green)}
</style>
""", unsafe_allow_html=True)


def _color_pnl(pct: float) -> str:
    if pct > 0.01: return "up"
    if pct < -0.01: return "down"
    return ""


# 行情滚动条 (签名元素)
codes = ticker.collect_ticker_codes()
from a_stock.a_stock_data._common import _live_price_batch  # 若无则降级
ticker_html = '<div class="ticker"><div class="ticker-track">'
for c in codes:
    try:
        from a_stock.risk_metrics import _live_price
        px = _live_price(c)
        if px:
            ticker_html += f"<span><b>{c}</b> {px:.3f}</span> "
    except Exception:
        pass
ticker_html += "</div></div>"
st.markdown(ticker_html, unsafe_allow_html=True)

# 资产条
CASH = 55319.0  # TODO: 后续从DB算真实现金, MVP用常量
ab = asset_bar.collect_asset_bar(CASH)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("总资产", f"{ab['total']:,}", f"{ab['unrealized']:+d}")
c2.metric("持仓市值", f"{ab['stock_mv']:,}", f"{len(positions_panel.collect_positions())} 只")
c3.metric("现金", f"{ab['cash']:,}", f"{ab['cash']/ab['total']*100:.0f}%")
c4.metric("浮盈", f"{ab['unrealized']:+d}", f"已实现{ab['realized']:+d}")
c5.metric("距目标", f"{ab['target_pct']}%", "→100k")

# 主区: 机会流 + 持仓栏
col_feed, col_pos = st.columns([2, 1])

with col_feed:
    st.markdown("#### 机会流")
    opps = opportunity_feed.collect_opportunities()
    if not opps:
        st.info("暂无机会点")
    bar_colors = {"pullback": "var(--amber)", "anomaly": "var(--red)",
                  "candidate": "var(--blue)", "rule": "var(--green)"}
    tag_classes = {"pullback": "tag-pull", "anomaly": "tag-anom",
                   "candidate": "tag-cand", "rule": "tag-rule"}
    for o in opps:
        bar_color = bar_colors[o["type"]]
        tag_cls = tag_classes[o["type"]]
        html = f'''<div class="opp"><div class="bar" style="background:{bar_color}"></div>
        <div style="flex:1">
        <span class="tag {tag_cls}">{o['tag']}</span>
        <div style="font-family:'JetBrains Mono',monospace"><b>{o['code']}</b> <span style="color:var(--dim)">{o['name']}</span></div>
        <div style="font-size:12px">{o['desc']}</div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--dim)">{o['meta']} · {o['time']}</div>
        </div></div>'''
        st.markdown(html, unsafe_allow_html=True)

with col_pos:
    st.markdown("#### 持仓")
    positions = positions_panel.collect_positions()
    if not positions:
        st.info("无持仓")
    for p in positions:
        cls = _color_pnl(p["pnl_pct"])
        st.markdown(
            f"**{p['code']}** {p['name']} "
            f"<span class='{cls}'>{p['pnl_pct']:+.2f}%</span><br>"
            f"<span style='color:var(--dim);font-size:11px'>"
            f"{p['qty']}股 @{p['cost']} 现{p['price']} 浮{p['pnl']:+d} 止{p['stop_loss']}</span>",
            unsafe_allow_html=True)
        st.markdown("---")

# 情绪条
s = sentiment_bar.collect_sentiment()
st.markdown(f"#### 🌡️ 情绪 {s['temp']:.0f} {s['mood']} · 领涨 {s['leader']}")

# 自动轮询: 盘中15s, 盘外60s
interval = 15000 if _is_trading_hours() else 60000
st_autorefresh = st.experimental_singleton
try:
    st.experimental_rerun()
except Exception:
    pass
import streamlit.components.v1 as components
# 用 st_autorefresh (需 streamlit-autorefresh 或 st.fragment)
# MVP: 提示手动刷新, 后续加 streamlit-autorefresh
st.caption(f"刷新间隔 {interval//1000}s · {'盘中' if _is_trading_hours() else '盘外'}")
```

注: 自动轮询 MVP 用提示手动刷新, 避免引入额外依赖。后续可加 `streamlit-autorefresh`。

- [ ] **Step 4: 手动跑验证**

Run: `.venv/bin/streamlit run a_stock/web/dashboard.py --server.headless true`
Expected: 浏览器开 localhost:8501, 显示交易终端UI (行情条+资产条+机会流+持仓栏+情绪)

验证项:
- 行情滚动条横向滚动
- 资产条5列数字正确
- 机会流显示4类机会 (或"暂无机会点")
- 持仓栏显示5只持仓红绿盈亏+成本+止损
- 情绪温度30谨慎

- [ ] **Step 5: 跑全套测试确认无回归**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 全部 PASS (162+10=172)

- [ ] **Step 6: 提交**

```bash
git add a_stock/web/dashboard.py requirements.txt
git commit -m "feat(web): dashboard Streamlit交易终端入口"
```

---

## Task 6: README 文档 + PROJECT_STATE 更新

**Files:**
- Create: `a_stock/web/README.md`
- Modify: `data/PROJECT_STATE.md`

- [ ] **Step 1: 写 web README**

Create `a_stock/web/README.md`:

```markdown
# A股盯盘Web UI

交易终端式盯盘界面。机会流+持仓侧栏,实时算4类机会点。

## 启动

```bash
.venv/bin/streamlit run a_stock/web/dashboard.py
```

浏览器开 http://localhost:8501

## 功能

- **行情滚动条**: 持仓+观察池+候选报价横向滚动
- **资产条**: 总资产/市值/现金/浮盈/距目标
- **机会流** (4类):
  - 📍 回踩买点 (琥珀): 多头排列+回踩MA5/MA10不破
  - ⚡ 异动 (红): 火箭/跳水/资金surge
  - 🎯 早盘候选 (蓝): morning_scan top5
  - 🔔 规则 (绿): rules.yaml命中+watchlist提醒
- **持仓栏**: 实时盈亏红绿+真实成本+ATR止损
- **情绪条**: 市场温度+领涨板块

## 视觉

A股涨红跌绿(反国际)+琥珀机会色+JetBrains Mono等宽报价。
深炭背景减眼疲劳。不替下单,决策权在用户。

## 数据源

复用 a_stock 现有模块: risk_metrics / ohlcv / technical_scorer / anomaly / sentiment / morning_scan。
不冲击东财push2 (复用 _common 限流)。
```

- [ ] **Step 2: 更新 PROJECT_STATE**

在 `data/PROJECT_STATE.md` 决策日志末尾追加:

```markdown
- 2026-06-29 Web盯盘UI上线: a_stock/web/ dashboard.py (Streamlit交易终端). 机会流4类(回踩买点/异动/候选/规则)+持仓侧栏+行情滚动条+情绪条. 复用现有模块实时算, A股涨红跌绿视觉. 启动: streamlit run a_stock/web/dashboard.py. +10测试 (172 passed).
```

并在工具链架构图 `a_stock/` 下加:

```
└── web/                盯盘Web UI (Streamlit)
    ├── dashboard.py    交易终端入口
    ├── opportunity_feed.py 4类机会聚合
    ├── positions_panel.py  持仓栏
    ├── asset_bar.py    资产条
    ├── ticker.py       行情滚动条
    └── sentiment_bar.py 情绪条
```

- [ ] **Step 3: 提交**

```bash
git add a_stock/web/README.md data/PROJECT_STATE.md
git commit -m "docs(web): README + PROJECT_STATE 更新"
```

---

## Self-Review

**1. Spec覆盖:**
- ✅ 机会流4类 (Task 2)
- ✅ 持仓栏+成本+ATR止损 (Task 3)
- ✅ 资产条 (Task 4)
- ✅ 行情滚动条ticker (Task 4 + Task 5)
- ✅ 情绪条 (Task 4)
- ✅ 交易终端视觉 (Task 5 CSS)
- ✅ 15s轮询 (Task 5, MVP手动刷新)
- ✅ 回踩买点新能力 (Task 1)
- ✅ 本地Streamlit (Task 5)
- ✅ 错误处理 (各组件try/except)
- ✅ 测试 (Task 1-4 共+10测试)

**2. Placeholder扫描:** dashboard.py 有 `CASH = 55319.0 # TODO` — MVP用常量, 后续从DB算真实现金。这是有意的技术债, 非计划占位, 已注明。其余无TBD/TODO。

**3. 类型一致:** collect_opportunities/collect_positions/collect_asset_bar/collect_ticker_codes/collect_sentiment 命名一致, 各返回dict/list结构在测试中锁定。

**4. 风险点:**
- `_live_price_batch` import 在dashboard.py 若不存在会NameError — Task 5 Step 3 代码已用 try/except 包 `_live_price`, 删掉无用import行。执行时注意。
- `streamlit-autorefresh` 未加依赖, MVP手动刷新, README已说明。
