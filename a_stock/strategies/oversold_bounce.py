"""超跌反弹策略 (抄 tickflow oversold_bounce.py).
触发: RSI<30 + 收阳 + 量比≥1.2"""
from .base import BaseStrategy, StrategyMeta


class OversoldBounce(BaseStrategy):
    META = StrategyMeta(
        id="oversold_bounce",
        name="超跌反弹",
        scoring={"rsi_14": 0.2, "vol_ratio_5d": 0.3, "change_pct": 0.5},
        stop_loss_pct=-0.05,
        max_hold_days=10,
    )

    def filter(self, df: dict) -> bool:
        rsi = df.get("rsi_14", 50)
        close = df.get("close", 0)
        open_ = df.get("open", 0)
        vol_ratio = df.get("vol_ratio_5d", 0)

        return rsi < 30 and close > open_ and vol_ratio >= 1.2
