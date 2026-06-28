"""资金流异动策略 (新增).
候选池来自 screener 已按净流入降序. 前10名 + 收涨 → 触发.
_rank 由 runner.run_all 注入 {code: 1-based_rank}."""
from a_stock.strategies.base import BaseStrategy, StrategyMeta
from a_stock.strategies.runner import build_indicators
from a_stock.strategies.signals import Signal


class MoneyflowSurge(BaseStrategy):
    META = StrategyMeta("moneyflow_surge", 0.6, "资金流异动: 净流入top10+收涨")
    _rank = None  # runner 注入 {code: rank}; None 时视为无排名

    def filter(self, code, name):
        return build_indicators(code) is not None

    def signals(self, code, name):
        rank = (self._rank or {}).get(code, 999)
        if rank > 10:
            return []
        ind = build_indicators(code)
        # 收涨: 末根 close > 前根 close
        if ind["last_close"] > ind["prev_close"]:
            return [Signal(code, name, "buy", 0.6, "moneyflow_surge",
                           f"资金流排名#{rank} 收涨{ind['change_pct']:+.1f}%",
                           {"price": ind["last_close"], "rank": rank})]
        return []
