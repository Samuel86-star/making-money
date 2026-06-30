"""A股盯盘Web UI — 交易终端. streamlit run a_stock/web/dashboard.py"""
import sys
from pathlib import Path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st
from datetime import datetime
from a_stock.risk_metrics import _live_price
from a_stock.web import opportunity_feed, positions_panel, asset_bar, ticker, sentiment_bar
from a_stock.web import trading_modal

# A股名称映射 (代码→中文), 行情条用
_NAMES = {
    "600276": "恒瑞医药", "515650": "消费50ETF", "300059": "东方财富",
    "159801": "芯片ETF", "159915": "创业板ETF", "159516": "半导体材料设备",
    "515880": "通信ETF", "000988": "华工科技", "000636": "风华高科",
    "300136": "信维通信", "002859": "洁美科技", "000021": "深科技",
    "000960": "锡业股份", "002407": "多氟多",
}


def _is_trading_hours() -> bool:
    now = datetime.now()
    t = now.hour * 60 + now.minute
    if now.weekday() >= 5:
        return False
    return (570 <= t <= 690) or (780 <= t <= 900)


def _pct_class(pct: float) -> str:
    if pct > 0.01:
        return "up"
    if pct < -0.01:
        return "down"
    return ""


st.set_page_config(page_title="A股盯盘 · 交易终端", page_icon="📊", layout="wide")

# === 设计token: 5色交易终端 + 等宽报价 ===
st.markdown("""<style>
:root{
  --bg:#0a0e14; --panel:#12161f; --panel-2:#161b26; --line:#1f2633; --line-2:#262d3b;
  --txt:#e8eaed; --dim:#7a8497; --dimmer:#4a5568;
  --red:#f23645; --green:#089981; --amber:#d4a017; --blue:#3b82f6;
  --mono:'JetBrains Mono','SF Mono',Menlo,ui-monospace,monospace;
  --sans:'Inter',-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;
}
.stApp{background:var(--bg);color:var(--txt);font-family:var(--sans);font-size:13px}
#MainMenu, footer, header[data-testid="stHeader"]{visibility:hidden}
.block-container{padding-top:1.2rem;padding-bottom:2rem;max-width:1280px}
/* 链接全局无下划线 (streamlit 注入的 a 样式会覆盖 .abtn/.newpos/.action) */
.stApp a,.stApp a:hover,.stApp a:visited{text-decoration:none !important}

/* 行情滚动条 (签名元素) */
.ticker{background:#000;border:1px solid var(--line);border-radius:6px;overflow:hidden;
  height:48px;display:flex;align-items:stretch;margin-bottom:18px;position:relative}
.ticker::before{content:'A股盯盘 · 实时';position:absolute;left:0;top:0;bottom:0;
  background:var(--red);color:#000;font-family:var(--mono);font-size:11px;font-weight:700;
  letter-spacing:0.08em;padding:0 14px;display:flex;align-items:center;z-index:2}
.ticker-track{display:flex;align-items:center;gap:32px;white-space:nowrap;
  animation:scroll 60s linear infinite;padding-left:120px;height:100%}
@keyframes scroll{from{transform:translateX(0)}to{transform:translateX(-50%)}}
@media(prefers-reduced-motion:reduce){.ticker-track{animation:none;padding-left:130px}}
.ticker-track .q{display:inline-flex;align-items:baseline;gap:6px}
.ticker-track .q .code{color:var(--dim);font-family:var(--mono);font-size:12px}
.ticker-track .q .name{color:var(--txt);font-size:13px;font-weight:500}
.ticker-track .q .px{font-family:var(--mono);font-size:13px;font-weight:600;color:var(--txt)}

/* 资产条 (5格紧贴) */
.bar5{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;background:var(--line);
  border:1px solid var(--line);border-radius:6px;overflow:hidden;margin-bottom:18px}
.kpi{background:var(--panel);padding:14px 18px;display:flex;flex-direction:column;gap:4px}
.kpi .lbl{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:0.12em;font-weight:500}
.kpi .val{font-family:var(--mono);font-size:26px;font-weight:600;line-height:1.1;color:var(--txt)}
.kpi .sub{font-family:var(--mono);font-size:11px;color:var(--dim)}
.kpi.hero .val{font-size:30px}

/* 机会流/持仓容器 */
.section-title{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:0.12em;
  font-weight:600;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between;gap:8px}
.section-title .left{display:flex;align-items:center;gap:8px}
.section-title .dot{width:6px;height:6px;border-radius:50%;background:var(--red);box-shadow:0 0 8px var(--red)}
.mood-mini{display:flex;align-items:center;gap:10px;font-family:var(--mono)}
.mood-mini .t{font-size:18px;font-weight:700;line-height:1}
.mood-mini .bar{width:60px;height:5px;background:var(--panel-2);border-radius:3px;overflow:hidden}
.mood-mini .fill{height:100%;background:linear-gradient(90deg,var(--green),var(--amber),var(--red))}
.mood-mini .lbl{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:0.1em}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;overflow:hidden}
.panel-scroll{max-height:420px;overflow-y:auto;scrollbar-width:thin;
  scrollbar-color:var(--line-2) transparent}
.panel-scroll::-webkit-scrollbar{width:6px}
.panel-scroll::-webkit-scrollbar-thumb{background:var(--line-2);border-radius:3px}
.panel-scroll::-webkit-scrollbar-track{background:transparent}

/* 机会卡片 (高度对齐持仓 card.hold) */
.opp{display:grid;grid-template-columns:3px 1fr auto;gap:14px;padding:12px 16px;
  border-bottom:1px solid var(--line);align-items:stretch;min-height:88px;height:88px;box-sizing:border-box}
.opp:last-child{border-bottom:0}
.opp .bar{width:3px;height:100%;border-radius:2px;align-self:stretch}
.opp .body{min-width:0;display:flex;flex-direction:column;gap:4px;justify-content:center}
.opp .top{display:flex;align-items:center;gap:8px;margin:0;line-height:1}
.opp .tag{font-size:10px;padding:2px 7px;border-radius:3px;font-weight:600;letter-spacing:0.04em;line-height:1.2}
.opp .code{font-family:var(--mono);font-weight:500;font-size:11px;color:var(--dimmer);margin-left:4px;line-height:1.2}
.opp .name{color:var(--txt);font-size:13px;font-weight:600;margin-left:4px;line-height:1.2}
.opp .desc{color:var(--txt);font-size:11.5px;line-height:1.2;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.opp .meta{font-family:var(--mono);font-size:10.5px;color:var(--dimmer);letter-spacing:0.02em;line-height:1.2}
.opp .action{align-self:center;font-family:var(--mono);font-size:12px;font-weight:600;
  padding:4px 9px;border-radius:4px;background:rgba(212,160,23,0.12);color:var(--amber);
  cursor:pointer;border:1px solid var(--amber);transition:all 0.15s;text-decoration:none}
.opp .action:hover{background:var(--amber);color:#000}
/* 持仓卡内 + - 文字链接 (股票名后) */
.abtn{color:var(--dim);font-family:var(--mono);font-size:11px;font-weight:600;
  margin-left:6px;padding:1px 5px;border:1px solid var(--line-2);border-radius:3px;
  text-decoration:none;transition:all 0.15s}
.abtn:hover{color:var(--red);border-color:var(--red);background:rgba(242,54,69,0.08)}
/* 持仓标题栏右侧 + 新建持仓 */
.section-title{position:relative}
.newpos{position:absolute;right:0;top:50%;transform:translateY(-50%);
  color:var(--dim);font-family:var(--mono);font-size:14px;font-weight:700;
  padding:1px 7px;border:1px solid var(--line-2);border-radius:3px;
  text-decoration:none;transition:all 0.15s}
.newpos:hover{color:var(--red);border-color:var(--red);background:rgba(242,54,69,0.08)}
.tag-pull{background:rgba(212,160,23,0.15);color:var(--amber)}
.tag-anom{background:rgba(242,54,69,0.15);color:var(--red)}
.tag-cand{background:rgba(59,130,246,0.15);color:var(--blue)}
.tag-rule{background:rgba(8,153,129,0.15);color:var(--green)}

/* 持仓栏 */
.hold{padding:12px 16px;border-bottom:1px solid var(--line)}
.hold:last-child{border-bottom:0}
.hold .r1{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:4px}
.hold .code{font-family:var(--mono);font-weight:600;font-size:13px}
.hold .name{color:var(--dim);font-size:11px;margin-left:6px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hold .pnl{font-family:var(--mono);font-weight:600;font-size:14px}
.hold .r2{display:flex;justify-content:space-between;font-family:var(--mono);font-size:10.5px;color:var(--dimmer);letter-spacing:0.02em}
.hold .r2 span b{color:var(--txt);font-weight:500}
.up{color:var(--red)} .down{color:var(--green)} .amber{color:var(--amber)}

.footer{text-align:center;color:var(--dimmer);font-size:10.5px;margin-top:18px;letter-spacing:0.08em;
  font-family:var(--mono);text-transform:uppercase}

/* 卡片行: 整行用 .card 容器, 按钮紧贴右侧 (streamlit columns) */
.card{display:grid;grid-template-columns:3px 1fr;gap:14px;padding:14px 16px;
  border-bottom:1px solid var(--line);align-items:center;min-height:70px;background:var(--panel)}
.card:last-child{border-bottom:0}
.card .bar{width:3px;height:36px;border-radius:2px}
.card .body{min-width:0}
.card .top{display:flex;align-items:center;gap:8px;margin-bottom:5px}
.card .tag{font-size:10px;padding:2px 7px;border-radius:3px;font-weight:600;letter-spacing:0.04em}
.card .code{font-family:var(--mono);font-weight:500;font-size:11px;color:var(--dimmer);margin-left:4px}
.card .name{color:var(--txt);font-size:13px;font-weight:600;margin-left:4px}
.card .desc{color:var(--txt);font-size:12.5px;line-height:1.4;margin:3px 0}
.card .meta{font-family:var(--mono);font-size:10.5px;color:var(--dimmer);letter-spacing:0.02em}

/* 持仓卡片变种 (3行信息, 跟 .opp 同高 88px) */
.card.hold{min-height:88px;height:88px;box-sizing:border-box;align-items:stretch;padding:12px 16px}
.card.hold .bar{height:100%;align-self:stretch}
.card.hold > .body{display:flex;flex-direction:column;gap:4px;justify-content:center}
.card.hold .r1{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0;line-height:1.2}
.card.hold .code{font-weight:600;font-size:13px;line-height:1.2}
.card.hold .pnl{font-family:var(--mono);font-weight:600;font-size:14px;margin-left:6px;line-height:1.2}
.card.hold .r2{display:flex;justify-content:space-between;font-family:var(--mono);font-size:10.5px;color:var(--dimmer);letter-spacing:0.02em;line-height:1.2;margin:0}
.card.hold .r2 b{color:var(--txt);font-weight:500}

/* 交易按钮: 紧凑文字按钮 (小不抢眼) */
.tbtn .stButton>button{height:24px;min-height:24px;padding:0 6px;font-size:11px;
  font-weight:600;border-radius:3px;border:1px solid var(--line-2);background:var(--panel-2);
  color:var(--dim);font-family:var(--mono);line-height:1;margin:0}
.tbtn .stButton>button:hover{border-color:var(--red);color:var(--red);background:rgba(242,54,69,0.08)}
.tbtn .stButton>button:focus{box-shadow:none;outline:none}
.tbtn .stButton>button:disabled{opacity:0.2;cursor:not-allowed}
.tbtn{margin:0;padding:0}
.tbtn [data-testid="stHorizontalBlock"]{gap:4px;margin:0;padding:0}
</style>""", unsafe_allow_html=True)


# === 行情滚动条 (签名元素) ===
codes = ticker.collect_ticker_codes()
ticker_quotes = []
for c in codes:
    try:
        px = _live_price(c)
        if px:
            name = _NAMES.get(c, "")
            ticker_quotes.append(f'<span class="q"><span class="code">{c}</span>'
                                 f'<span class="name">{name}</span>'
                                 f'<span class="px">{px:.3f}</span></span>')
    except Exception:
        pass
track = " ".join(ticker_quotes + ticker_quotes)
st.markdown(f'<div class="ticker"><div class="ticker-track">{track}</div></div>',
            unsafe_allow_html=True)


# === 资产条 ===
ab = asset_bar.collect_asset_bar(55319.0)
n_pos = len(positions_panel.collect_positions())
cash_pct = ab["cash"] / max(ab["total"], 1) * 100
st.markdown(f"""<div class="bar5">
<div class="kpi hero"><span class="lbl">总资产</span><span class="val">{ab['total']:,}</span>
  <span class="sub up">浮盈 {ab['unrealized']:+d} · 已实现 {ab['realized']:+d}</span></div>
<div class="kpi"><span class="lbl">持仓市值</span><span class="val">{ab['stock_mv']:,}</span>
  <span class="sub">{n_pos} 只标的</span></div>
<div class="kpi"><span class="lbl">现金</span><span class="val">{ab['cash']:,}</span>
  <span class="sub">弹药 {cash_pct:.0f}%</span></div>
<div class="kpi"><span class="lbl">浮盈</span><span class="val up">{ab['unrealized']:+d}</span>
  <span class="sub">日已实现 {ab['realized']:+d}</span></div>
<div class="kpi"><span class="lbl">距 100k</span><span class="val amber">{ab['target_pct']}%</span>
  <span class="sub">→ 100,000</span></div>
</div>""", unsafe_allow_html=True)


# === 主区: 机会流 + 持仓栏 ===
bar_colors = {"pullback": "var(--amber)", "anomaly": "var(--red)",
              "candidate": "var(--blue)", "rule": "var(--green)"}
tag_classes = {"pullback": "tag-pull", "anomaly": "tag-anom",
               "candidate": "tag-cand", "rule": "tag-rule"}
type_label = {"pullback": "回踩买点", "anomaly": "盘中异动",
              "candidate": "早盘候选", "rule": "规则触发"}

col_feed, col_pos = st.columns([2, 1])

# 情绪: 提到 col_feed 块前, 标题和footer共用
s = sentiment_bar.collect_sentiment()

with col_feed:
    mood_color = ("var(--red)" if s["temp"] >= 55
                  else ("var(--amber)" if s["temp"] >= 30 else "var(--green)"))
    st.markdown(f"""<div class="section-title">
<div class="left"><span class="dot"></span>机会流</div>
<div class="mood-mini"><span class="t" style="color:{mood_color}">{s['temp']:.0f}</span>
<div class="bar"><div class="fill" style="width:{s['temp']:.0f}%"></div></div>
<span class="lbl">{s['mood'] or '中性'}</span></div>
</div>""", unsafe_allow_html=True)
    opps = opportunity_feed.collect_opportunities()
    if not opps:
        st.markdown('<div class="panel" style="padding:40px;text-align:center;color:var(--dim)">'
                    '暂无机会点 · 盘后或市场平静时属正常</div>', unsafe_allow_html=True)
    else:
        # 纯HTML卡片. action 区用 <a href="?action=add&code=..."> 触发 streamlit query_params
        rows_html = []
        for o in opps:
            bar_color = bar_colors[o["type"]]
            tag_cls = tag_classes[o["type"]]
            name = o.get("name") or ""
            code = o["code"]
            cost = o.get("cost", 0.0)
            label = o.get("action_label") or "加仓"
            rows_html.append(f"""<div class="opp">
<div class="bar" style="background:{bar_color}"></div>
<div class="body">
<div class="top"><span class="tag {tag_cls}">{type_label[o['type']]}</span>
<span class="code">{o['code']}</span><span class="name">{name}</span></div>
<div class="desc">{o['desc']}</div>
<div class="meta">{o['meta']} · {o['time']}</div>
</div>
<a class="action" href="?action=add&code={code}&name={name}&cost={cost}"
   target="_self">{label}</a>
</div>""")
        st.markdown('<div class="panel panel-scroll">' + "".join(rows_html) + '</div>',
                    unsafe_allow_html=True)

with col_pos:
    st.markdown('<div class="section-title"><span class="left">'
                '<span class="dot"></span><span style="color:var(--dim)">持仓</span></span>'
                '<a class="newpos" href="?action=new" target="_self" title="新建持仓">+</a>'
                '</div>',
                unsafe_allow_html=True)
    positions = positions_panel.collect_positions()
    if not positions:
        st.markdown('<div class="panel" style="padding:40px;text-align:center;color:var(--dim)">'
                    '无持仓</div>', unsafe_allow_html=True)
    else:
        # 卡片面板 + 股票名后 +/- 链接 (query string 触发)
        rows = []
        for p in positions:
            cls = _pct_class(p["pnl_pct"])
            sl = p["stop_loss"] if p["stop_loss"] else "—"
            code = p["code"]
            name = p["name"]
            cost = p["cost"]
            qty = p["qty"]
            rows.append(f"""<div class="card hold">
<div class="bar" style="background:var(--red)"></div>
<div class="body">
<div class="r1"><div><span class="code">{p['code']}</span>
<span class="name">{p['name']}</span>
<a class="abtn" href="?action=add&code={code}&name={name}&cost={cost}" target="_self">+</a>
<a class="abtn" href="?action=reduce&code={code}&name={name}&qty={qty}&cost={cost}" target="_self">-</a>
</div>
<span class="pnl {cls}">{p['pnl_pct']:+.2f}%</span></div>
<div class="r2"><span>{p['qty']}股 @<b>{p['cost']}</b></span>
<span>现 <b>{p['price']}</b></span></div>
<div class="r2"><span>浮 <b class="{cls}">{p['pnl']:+d}</b></span>
<span>ATR止损 <b>{sl}</b></span></div>
</div></div>""")
        st.markdown('<div class="panel">' + "".join(rows) + '</div>',
                    unsafe_allow_html=True)


phase = "盘中" if _is_trading_hours() else "盘外"
st.markdown(f'<div class="footer">{phase} · {s["leader"] or "—"} · 手动刷新 · 决策权在你</div>',
            unsafe_allow_html=True)


# === 交易弹窗触发 (query_params → dialog, 卡片用 <a href> 触发) ===
_qp = st.query_params
if "action" in _qp:
    action = _qp["action"]
    if action == "add":
        trading_modal.open_add(_qp.get("code", ""), _qp.get("name", ""),
                                float(_qp.get("cost", 0) or 0))
    elif action == "reduce":
        trading_modal.open_reduce(_qp.get("code", ""), _qp.get("name", ""),
                                   int(_qp.get("qty", 100) or 100),
                                   float(_qp.get("cost", 0) or 0))
    elif action == "new":
        trading_modal.open_new_position()
    st.query_params.clear()
