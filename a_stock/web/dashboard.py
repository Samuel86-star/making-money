"""A股盯盘Web UI — 交易终端. streamlit run a_stock/web/dashboard.py"""
import streamlit as st
from datetime import datetime
from a_stock.web import opportunity_feed, positions_panel, asset_bar, ticker, sentiment_bar


def _is_trading_hours() -> bool:
    """A股交易时段 9:30-11:30, 13:00-15:00 周一至五."""
    now = datetime.now()
    t = now.hour * 60 + now.minute
    if now.weekday() >= 5:
        return False
    return (570 <= t <= 690) or (780 <= t <= 900)


def _color_pnl(pct: float) -> str:
    if pct > 0.01:
        return "up"
    if pct < -0.01:
        return "down"
    return ""


st.set_page_config(page_title="A股盯盘", page_icon="📊", layout="wide")

# CSS: 交易终端视觉 (A股涨红跌绿, 反国际)
st.markdown("""
<style>
:root{--bg:#0a0e14;--panel:#12161f;--line:#1f2633;--txt:#e8eaed;--dim:#6b7280;
--red:#f23645;--green:#089981;--amber:#d4a017;--blue:#3b82f6;}
.stApp{background:var(--bg);color:var(--txt);font-family:'Inter','PingFang SC',sans-serif;}
.stMarkdown,.stMarkdown p{color:var(--txt)!important}
.block-container{padding-top:1rem;max-width:1200px}
.ticker{background:#000;border:1px solid var(--line);border-radius:6px;overflow:hidden;
height:34px;display:flex;align-items:center;margin-bottom:14px}
.ticker-track{display:flex;gap:24px;white-space:nowrap;animation:scroll 40s linear infinite;
font-family:'JetBrains Mono','SF Mono',monospace;font-size:12px;padding-left:100%}
@keyframes scroll{to{transform:translateX(-100%)}}
@media(prefers-reduced-motion:reduce){.ticker-track{animation:none;padding-left:16px}}
.up{color:var(--red)} .down{color:var(--green)} .amber{color:var(--amber)}
.opp{display:flex;gap:12px;padding:12px 14px;border-bottom:1px solid var(--line);align-items:flex-start}
.opp .bar{width:3px;align-self:stretch;border-radius:2px}
.opp .tag{font-size:10px;padding:1px 6px;border-radius:3px;font-weight:600}
.tag-pull{background:rgba(212,160,23,.15);color:var(--amber)}
.tag-anom{background:rgba(242,54,69,.15);color:var(--red)}
.tag-cand{background:rgba(59,130,246,.15);color:var(--blue)}
.tag-rule{background:rgba(8,153,129,.15);color:var(--green)}
.pos-item{padding:10px 0;border-bottom:1px solid var(--line)}
</style>
""", unsafe_allow_html=True)

# === 行情滚动条 (签名元素) ===
codes = ticker.collect_ticker_codes()
from a_stock.risk_metrics import _live_price
ticker_parts = []
for c in codes:
    try:
        px = _live_price(c)
        if px:
            ticker_parts.append(f"<span><b>{c}</b> {px:.3f}</span>")
    except Exception:
        pass
ticker_html = '<div class="ticker"><div class="ticker-track">' + " ".join(ticker_parts) + "</div></div>"
st.markdown(ticker_html, unsafe_allow_html=True)

# === 资产条 ===
CASH = 55319.0  # MVP: 后续从DB算真实现金
ab = asset_bar.collect_asset_bar(CASH)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("总资产", f"{ab['total']:,}", f"{ab['unrealized']:+d}")
c2.metric("持仓市值", f"{ab['stock_mv']:,}", f"{len(positions_panel.collect_positions())} 只")
c3.metric("现金", f"{ab['cash']:,}", f"{ab['cash']/max(ab['total'],1)*100:.0f}%")
c4.metric("浮盈", f"{ab['unrealized']:+d}", f"已实现{ab['realized']:+d}")
c5.metric("距目标", f"{ab['target_pct']}%", "→100k")

# === 主区: 机会流 + 持仓栏 ===
col_feed, col_pos = st.columns([2, 1])

bar_colors = {"pullback": "var(--amber)", "anomaly": "var(--red)",
              "candidate": "var(--blue)", "rule": "var(--green)"}
tag_classes = {"pullback": "tag-pull", "anomaly": "tag-anom",
               "candidate": "tag-cand", "rule": "tag-rule"}

with col_feed:
    st.markdown("#### 机会流")
    opps = opportunity_feed.collect_opportunities()
    if not opps:
        st.info("暂无机会点")
    for o in opps:
        bar_color = bar_colors[o["type"]]
        tag_cls = tag_classes[o["type"]]
        action = f"<span class='amber'>{o['action_label']}</span>" if o.get("action_label") else ""
        html = f"""<div class="opp"><div class="bar" style="background:{bar_color}"></div>
        <div style="flex:1">
        <span class="tag {tag_cls}">{o['tag']}</span> {action}
        <div style="font-family:'JetBrains Mono',monospace"><b>{o['code']}</b>
        <span style="color:var(--dim)">{o['name']}</span></div>
        <div style="font-size:12px">{o['desc']}</div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--dim)">{o['meta']} · {o['time']}</div>
        </div></div>"""
        st.markdown(html, unsafe_allow_html=True)

with col_pos:
    st.markdown("#### 持仓")
    positions = positions_panel.collect_positions()
    if not positions:
        st.info("无持仓")
    for p in positions:
        cls = _color_pnl(p["pnl_pct"])
        sl = p["stop_loss"] if p["stop_loss"] else "-"
        st.markdown(
            f"<div class='pos-item'><b>{p['code']}</b> {p['name']} "
            f"<span class='{cls}'>{p['pnl_pct']:+.2f}%</span><br>"
            f"<span style='color:var(--dim);font-size:11px'>"
            f"{p['qty']}股 @{p['cost']} 现{p['price']} 浮{p['pnl']:+d} 止{sl}</span></div>",
            unsafe_allow_html=True)

# === 情绪条 ===
s = sentiment_bar.collect_sentiment()
st.markdown(f"#### 🌡️ 情绪 {s['temp']:.0f} {s['mood']} · 领涨 {s['leader'] or '-'}")

st.caption(f"刷新: 手动点浏览器刷新 · {'盘中' if _is_trading_hours() else '盘外'} · 不替下单, 决策权在你")