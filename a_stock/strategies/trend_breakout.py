"""趋势突破策略 (抄 tickflow trend_breakout.py).
触发: close>ma60 + 60日新高 + 量比≥2. confidence 0.7."""
from a_stock.strategies.base import BaseStrategy, StrategyMeta
from a_stock.strategies.runner import build_indicators
from a_stock.strategies.signals import Signal


class TrendBreakout(BaseStrategy):
    META = StrategyMeta("trend_breakout", 0.7, "趋势突破: 站上60日线+60日新高+量比≥2")

    def filter(self, code, name):
        ind = build_indicators(code)
        return ind is not None and len(ind["df"]) >= 60

    def signals(self, code, name):
        ind = build_indicators(code)
        last = ind["df"].iloc[-1]
        # 60日新高: 末根 high 达到 60日高点 (high_60d 含末根 high, 新高时二者相等).
        # 用 high 而非 close: close 永远 ≤ 当日 high, 拿 close 比当日 high 会恒 False.
        cond = (
            last["close"] > ind["ma60"]
            and last["high"] >= ind["high_60d"]
            and ind["vol_ratio"] >= 2.0
        )
        if cond:
            return [Signal(code, name, "buy", 0.7, "trend_breakout",
                           f"突破60日新高{ind['high_60d']:.2f} 量比{ind['vol_ratio']:.1f}",
                           {"price": ind["last_close"], "ma60": ind["ma60"]})]
        return []
