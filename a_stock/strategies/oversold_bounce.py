"""超跌反弹策略 (抄 tickflow oversold_bounce.py).
触发: RSI<30 + 收阳 + 量比≥1.2. confidence 0.5."""
from a_stock.strategies.base import BaseStrategy, StrategyMeta
from a_stock.strategies.runner import build_indicators, _rsi
from a_stock.strategies.signals import Signal


class OversoldBounce(BaseStrategy):
    META = StrategyMeta("oversold_bounce", 0.5, "超跌反弹: RSI<30+收阳+量比≥1.2")

    def filter(self, code, name):
        return build_indicators(code) is not None

    def signals(self, code, name):
        ind = build_indicators(code)
        df = ind["df"]
        last = df.iloc[-1]
        # RSI 取末根前一日的状态: 末根是反弹阳线, 其本身拉高 RSI,
        # 用全序列末根 RSI 会把超跌信号抹掉. 取 closes.iloc[:-1] 的 RSI 反映反弹前的超跌.
        rsi = _rsi(df["close"].iloc[:-1]) if len(df) > 15 else ind["rsi"]
        cond = (
            rsi < 30
            and last["close"] > last["open"]   # 收阳
            and ind["vol_ratio"] >= 1.2
        )
        if cond:
            return [Signal(code, name, "buy", 0.5, "oversold_bounce",
                           f"RSI{rsi:.0f}超跌 量比{ind['vol_ratio']:.1f}",
                           {"price": ind["last_close"], "rsi": rsi})]
        return []
