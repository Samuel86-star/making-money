"""逼近涨停策略 (抄 tickflow near_limit_up.py).
触发: 涨>7% 且 距涨停<3% (盘后选股, 未封板)"""
from .base import BaseStrategy, StrategyMeta, limit_pct


class NearLimitUp(BaseStrategy):
    META = StrategyMeta(
        id="near_limit_up",
        name="逼近涨停",
        scoring={"change_pct": 0.5, "vol_ratio_5d": 0.3, "momentum_5d": 0.2},
        stop_loss_pct=-0.05,
        max_hold_days=5,
    )

    def filter(self, df: dict) -> bool:
        change_pct = df.get("change_pct", 0)
        code = df.get("code", "")
        name = df.get("name", "")

        if change_pct < 7:
            return False
        # 距涨停<3% 但未封板
        lp = limit_pct(code, name)
        return change_pct < (lp * 100 - 3)
