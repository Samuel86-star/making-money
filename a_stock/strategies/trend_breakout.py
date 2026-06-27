"""趋势突破策略 (抄 tickflow trend_breakout.py).
触发: close>ma60 + 60日新高 + 量比≥2"""
from .base import BaseStrategy, StrategyMeta


class TrendBreakout(BaseStrategy):
    META = StrategyMeta(
        id="trend_breakout",
        name="趋势突破",
        scoring={"momentum_60d": 0.4, "vol_ratio_5d": 0.3, "change_pct": 0.3},
        stop_loss_pct=-0.08,
        max_hold_days=20,
    )

    def filter(self, df: dict) -> bool:
        close = df.get("close", 0)
        ma60 = df.get("ma60", 0)
        high_60d = df.get("high_60d", 0)
        vol_ratio = df.get("vol_ratio_5d", 0)

        if not (close and ma60 and high_60d):
            return False
        # 价上ma60 + 创60日新高 + 量比≥2
        return close > ma60 and close >= high_60d * 0.98 and vol_ratio >= 2.0
