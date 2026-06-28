"""逼近涨停策略 (抄 tickflow near_limit_up.py).
触发: 涨>7% 且 距涨停<3% (未封板). confidence 0.6.
盘后选股逻辑: 已封板(距涨停≈0)不选, 留次日空间.
依赖 change_pct = 涨跌幅 (close vs prev_close), 由 build_indicators 提供."""
from a_stock.strategies.base import BaseStrategy, StrategyMeta, limit_pct
from a_stock.strategies.runner import build_indicators
from a_stock.strategies.signals import Signal


class NearLimitUp(BaseStrategy):
    META = StrategyMeta("near_limit_up", 0.6, "逼近涨停: 涨>7%+距涨停<3%+未封板")

    def filter(self, code, name):
        return build_indicators(code) is not None

    def signals(self, code, name):
        ind = build_indicators(code)
        last = ind["df"].iloc[-1]
        change_pct = ind["change_pct"]  # 涨跌幅 (close vs prev_close)
        limit = limit_pct(code)
        dist_to_limit = limit - change_pct
        # 未封板: 当日 high 未触及涨停价 (触及=封板, 不留次日空间).
        # 涨停价 = prev_close * (1 + limit/100).
        limit_price = ind["prev_close"] * (1 + limit / 100)
        cond = (change_pct > 7 and 0 < dist_to_limit < 3
                and last["high"] < limit_price)
        if cond:
            return [Signal(code, name, "buy", 0.6, "near_limit_up",
                           f"涨{change_pct:.1f}% 距涨停{dist_to_limit:.1f}%",
                           {"price": ind["last_close"], "change_pct": change_pct})]
        return []
