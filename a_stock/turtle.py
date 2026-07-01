"""Turtle 趋势跟踪系统 (学习路径 P2).

核心规则 (海龟交易法则):
- 入场: System 1 = 20日唐奇安突破; System 2 = 55日突破 (更强).
- 止损: 入场 - 2×ATR (N). 每Unit风险 = 资本×1%.
- 单位: unit_shares = (资本×1%) / (2×ATR每股).
- 金字塔加仓: 每 +0.5N 有利波动加1 Unit, 最多4 Unit. 加仓后止损上移0.5N.
- 退出: System 1 多头跌破10日低; System 2 跌破20日低.

属纯计算模块, 不下单. 给 morning_scan/rules.yaml 提供突破信号 + Turtle 风险参数.
ATR 复用 a_stock.ohlcv.atr (Wilder SMA 简化版).
"""
import argparse
from dataclasses import dataclass, field

import a_stock.ohlcv as ohlcv


def donchian(closes: list[float], n: int) -> tuple[float, float]:
    """唐奇安通道: 近 n 日(排除当日)最高/最低. 数据不足返回当日价."""
    if len(closes) < n + 1:
        return closes[-1], closes[-1]
    window = closes[-n - 1:-1]
    return max(window), min(window)


def breakout_signal(closes: list[float]) -> str | None:
    """突破信号: 'sys2_breakout'(55日, 强) > 'sys1_breakout'(20日). 无返回None."""
    if len(closes) < 56:
        return None
    price = closes[-1]
    dc20_h, _ = donchian(closes, 20)
    dc55_h, _ = donchian(closes, 55)
    if price > dc55_h:
        return "sys2_breakout"
    if price > dc20_h:
        return "sys1_breakout"
    return None


def exit_signal(closes: list[float], sys: int = 1) -> str | None:
    """退出信号 (多头): sys1 跌破10日低; sys2 跌破20日低. 无返回None."""
    n = 10 if sys == 1 else 20
    if len(closes) < n + 1:
        return None
    price = closes[-1]
    _, low_n = donchian(closes, n)
    return "exit_long" if price < low_n else None


def turtle_stop(entry: float, atr_val: float | None) -> float | None:
    """入场 - 2×ATR (纯 Turtle 纪律, 无地板; 与 ohlcv.struct_stop_loss 区别在那有2%地板)."""
    if not atr_val or atr_val <= 0:
        return None
    return entry - 2 * atr_val


def unit_size(capital: float, atr_val: float | None, risk_pct: float = 0.01) -> int:
    """1 Unit 股数 = (资本×risk_pct) / (2×ATR每股), 取整100手 (A股). ATR=每股波幅."""
    if not atr_val or atr_val <= 0:
        return 0
    risk_amount = capital * risk_pct
    stop_per_share = 2 * atr_val
    shares = int(risk_amount / stop_per_share)
    return max(shares // 100 * 100, 0)


def pyramid_plan(entry: float, atr_val: float | None, max_units: int = 4) -> list[float]:
    """金字塔加仓触发价: 每 +0.5N 加1 Unit. 返回加仓价(不含首仓), 最多 max_units-1 个."""
    if not atr_val or atr_val <= 0 or max_units <= 1:
        return []
    return [round(entry + 0.5 * atr_val * i, 3) for i in range(1, max_units)]


@dataclass
class TurtleSignal:
    code: str
    price: float
    signal: str | None               # sys1_breakout / sys2_breakout / None
    dc20_high: float
    dc20_low: float
    dc55_high: float
    atr: float | None
    entry: float | None = None       # 突破价 (有信号时=dc_high)
    stop: float | None = None        # entry - 2N
    unit_shares: int = 0             # 1 Unit (1%风险)
    pyramid: list[float] = field(default_factory=list)
    note: str = ""


def analyze(code: str, capital: float = 79938.0, risk_pct: float = 0.01) -> TurtleSignal | None:
    """分析单只: 拉OHLCV → 算Donchian/突破/ATR/止损/单位/金字塔. 无数据返回None."""
    try:
        df = ohlcv.load_ohlcv(code)
    except Exception:
        return None
    if len(df) < 21:
        return None
    closes = df["close"].astype(float).tolist()
    price = closes[-1]
    dc20_h, dc20_low = donchian(closes, 20)
    dc55_h, _ = donchian(closes, 55) if len(closes) >= 56 else (dc20_h, dc20_low)
    sig = breakout_signal(closes)
    atr_val = ohlcv.atr(code)
    entry = None
    stop = None
    pyramid = []
    note = ""
    if sig:
        entry = dc55_h if sig == "sys2_breakout" else dc20_h
        stop = turtle_stop(entry, atr_val)
        pyramid = pyramid_plan(entry, atr_val)
        note = f"突破入场@{entry:.3f}, 止损{stop:.3f}" if stop else f"突破但ATR缺失"
    return TurtleSignal(
        code=code, price=price, signal=sig,
        dc20_high=dc20_h, dc20_low=dc20_low, dc55_high=dc55_h,
        atr=atr_val, entry=entry, stop=stop,
        unit_shares=unit_size(capital, atr_val, risk_pct),
        pyramid=pyramid, note=note,
    )


_WATCHLIST = [
    ("515650", "消费50ETF"), ("600276", "恒瑞医药"), ("300059", "东方财富"),
    ("159801", "芯片ETF广发"), ("159915", "创业板ETF"), ("515880", "通信ETF"),
    ("159516", "半导体材料ETF"),
]


def main():
    ap = argparse.ArgumentParser(description="Turtle 趋势跟踪: Donchian突破 + 2N止损 + 1%单位")
    ap.add_argument("--capital", type=float, default=79938.0)
    ap.add_argument("--risk", type=float, default=0.01, help="每Unit风险占比, 默认1%")
    args = ap.parse_args()

    print(f"=== Turtle 信号 (资本 {args.capital:,.0f}, 每 Unit 风险 {args.risk:.0%}) ===\n")
    print(f"{'代码':<8}{'现价':>8}  {'信号':<14}{'DC20高/低':<16}{'ATR':>7} "
          f"{'入场':>8}{'止损':>8}{'1Unit股':>8}  金字塔")
    for code, name in _WATCHLIST:
        t = analyze(code, args.capital, args.risk)
        if t is None:
            print(f"{code} {name}: 数据不足")
            continue
        sig = t.signal or "—"
        dc = f"{t.dc20_high:.3f}/{t.dc20_low:.3f}"
        atr = f"{t.atr:.3f}" if t.atr else "—"
        entry = f"{t.entry:.3f}" if t.entry else "—"
        stop = f"{t.stop:.3f}" if t.stop else "—"
        pyr = ",".join(f"{p:.3f}" for p in t.pyramid) if t.pyramid else "—"
        print(f"{code:<8}{t.price:>8.3f}  {sig:<14}{dc:<16}{atr:>7} "
              f"{entry:>8}{stop:>8}{t.unit_shares:>8}  {pyr}  ({name})")


if __name__ == "__main__":
    main()
