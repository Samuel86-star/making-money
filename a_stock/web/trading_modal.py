"""交易弹窗工具: 加仓/减仓/新建持仓 表单 + 100股铁律校验 + 选最大lot.

保留 _validate_lot / _pick_largest_lot 作为dashboard和测试共用工具.
弹窗走 st.dialog, 由 dashboard 顶层 session_state 触发.
"""
import streamlit as st
from a_stock.a_screen.decision_log import add_add, reduce_position, add_buy
from a_stock.risk_metrics import _live_price


def _validate_lot(qty: int, action: str = "add") -> tuple[bool, str]:
    """A股100股整数倍校验. action=add时只校验≥100的整数倍, 减仓额外校验≤持仓."""
    if qty <= 0:
        return False, "数量必须 > 0"
    if qty % 100 != 0:
        return False, f"A股必须100整数倍, 当前 {qty}"
    if action == "add" and qty < 100:
        return False, "买入至少100股"
    return True, ""


def _pick_largest_lot(code: str) -> int | None:
    """减仓时自动选最大剩余量的lot (parent_id)."""
    from a_stock.a_screen.decision_log import cost_report
    rep = cost_report(code)
    if not rep:
        return None
    lots_with_remain = [lot for lot in rep["lots"] if lot["remaining"] > 0]
    if not lots_with_remain:
        return None
    return max(lots_with_remain, key=lambda x: x["remaining"])["id"]


@st.dialog("➕ 加仓", width="small")
def open_add(code: str, name: str, cost: float = 0.0):
    """加仓弹窗. 默认填入当前成本+现价, 用户调整."""
    current_px = _live_price(code) or cost
    with st.form(f"add_dialog_{code}", clear_on_submit=True):
        st.caption(f"{name} ({code})")
        col1, col2 = st.columns(2)
        with col1:
            price = st.number_input("买入价 ¥", min_value=0.001, max_value=10000.0,
                                     value=float(current_px), step=0.01, format="%.3f",
                                     key=f"ad_px_{code}")
        with col2:
            qty = st.number_input("数量(股)", min_value=100, max_value=1_000_000,
                                   value=100, step=100, key=f"ad_qty_{code}")
        strategy = st.radio("策略", ["mid", "short"], horizontal=True,
                            key=f"ad_strat_{code}")
        reason = st.text_input("理由 (可选)", key=f"ad_r_{code}",
                                placeholder="回踩MA5加仓 / 突破前高加仓")
        col_ok, col_cancel = st.columns([1, 1])
        with col_ok:
            submit = st.form_submit_button("确认加仓", type="primary",
                                            use_container_width=True)
        with col_cancel:
            cancel = st.form_submit_button("取消", use_container_width=True)
        if cancel:
            st.rerun()
        if submit:
            ok, msg = _validate_lot(int(qty), "add")
            if not ok:
                st.error(f"❌ {msg}")
                return
            if price <= 0:
                st.error("❌ 买入价必须 > 0")
                return
            try:
                new_id = add_add(code=code, strategy=strategy, price=price,
                                 quantity=int(qty), reason=reason or None)
                st.success(f"✅ 加仓成功 id={new_id} · {code} {qty}股 @{price}")
                import time; time.sleep(0.6)
                st.rerun()
            except Exception as e:
                st.error(f"❌ 写入失败: {e}")


@st.dialog("➖ 减仓", width="small")
def open_reduce(code: str, name: str, qty_held: int, cost: float):
    """减仓弹窗. 默认减全部 (取整手)."""
    current_px = _live_price(code) or cost
    default_qty = (qty_held // 100) * 100
    if default_qty < 100 and qty_held >= 100:
        default_qty = 100
    with st.form(f"red_dialog_{code}", clear_on_submit=True):
        st.caption(f"{name} ({code}) · 持仓 {qty_held}股")
        col1, col2 = st.columns(2)
        with col1:
            price = st.number_input("卖出价 ¥", min_value=0.001, max_value=10000.0,
                                     value=float(current_px), step=0.01, format="%.3f",
                                     key=f"rd_px_{code}")
        with col2:
            qty = st.number_input("数量(股)", min_value=100,
                                   max_value=max(qty_held, 100),
                                   value=int(default_qty) if default_qty >= 100 else 100,
                                   step=100, key=f"rd_qty_{code}")
        reason = st.selectbox("原因", ["partial_take_profit", "partial_stop_loss", "manual"],
                               key=f"rd_reason_{code}")
        st.caption(f"💰 预估实现: {(price - cost) * qty:+.0f}元 (成本{cost:.4f})")
        col_ok, col_cancel = st.columns([1, 1])
        with col_ok:
            submit = st.form_submit_button("确认减仓", type="primary",
                                            use_container_width=True)
        with col_cancel:
            cancel = st.form_submit_button("取消", use_container_width=True)
        if cancel:
            st.rerun()
        if submit:
            ok, msg = _validate_lot(int(qty), "reduce")
            if not ok:
                st.error(f"❌ {msg}")
                return
            if qty > qty_held:
                st.error(f"❌ 减仓数量 {qty} 超过持仓 {qty_held}")
                return
            if price <= 0:
                st.error("❌ 卖出价必须 > 0")
                return
            parent_id = _pick_largest_lot(code)
            if not parent_id:
                st.error(f"❌ {code} 无可减仓lot")
                return
            try:
                new_id = reduce_position(parent_id=parent_id, reduce_price=price,
                                          reduce_qty=int(qty), reason=reason)
                st.success(f"✅ 减仓成功 id={new_id} · {code} {qty}股 @{price}")
                import time; time.sleep(0.6)
                st.rerun()
            except Exception as e:
                st.error(f"❌ 写入失败: {e}")


@st.dialog("➕ 新建持仓", width="small")
def open_new_position():
    """持仓标题栏 ➕ → 弹新建持仓窗 (录入: 编号/名称/成本/数量)."""
    with st.form("new_pos_dialog", clear_on_submit=True):
        code = st.text_input("股票代码", placeholder="000960 / 515650",
                              key="np_code").strip()
        name = st.text_input("股票名称 (可后填)", placeholder="锡业股份",
                              key="np_name").strip()
        col1, col2 = st.columns(2)
        with col1:
            price = st.number_input("成本价 ¥", min_value=0.001, max_value=10000.0,
                                     value=1.0, step=0.01, format="%.3f", key="np_px")
        with col2:
            qty = st.number_input("数量(股)", min_value=100, max_value=1_000_000,
                                   value=100, step=100, key="np_qty")
        strategy = st.radio("策略", ["mid", "short"], horizontal=True, key="np_strat")
        reason = st.text_input("买入理由 (可选)", key="np_r",
                                placeholder="回踩买点 / 突破前高 / 试仓")
        col_ok, col_cancel = st.columns([1, 1])
        with col_ok:
            submit = st.form_submit_button("确认建仓", type="primary",
                                            use_container_width=True)
        with col_cancel:
            cancel = st.form_submit_button("取消", use_container_width=True)
        if cancel:
            st.rerun()
        if submit:
            if not code or not code.isdigit() or not (5 <= len(code) <= 6):
                st.error("❌ 代码需 5-6 位数字")
                return
            ok, msg = _validate_lot(int(qty), "add")
            if not ok:
                st.error(f"❌ {msg}")
                return
            if price <= 0:
                st.error("❌ 成本价必须 > 0")
                return
            try:
                new_id = add_buy(
                    code=code, name=name or code, strategy=strategy,
                    price=price, quantity=int(qty), reason=reason or None,
                )
                st.success(f"✅ 建仓成功 id={new_id} · {name or code}({code}) "
                            f"{qty}股 @{price}")
                import time; time.sleep(0.8)
                st.rerun()
            except Exception as e:
                st.error(f"❌ 写入失败: {e}")
