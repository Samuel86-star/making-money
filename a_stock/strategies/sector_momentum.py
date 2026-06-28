"""板块动量策略 (新增).
设计偏离 spec: sectors.py 无板块→成分股接口, 改用 sector_rotation verdict 作市场门.
触发: 轮动 verdict=='持续主线' 且候选日内涨>3%. confidence 0.5.
逻辑: 主线确立时, 强势候选获动量加分."""
from a_stock.strategies.base import BaseStrategy, StrategyMeta
from a_stock.strategies.runner import build_indicators
from a_stock.strategies.signals import Signal


def _analyze():
    """封装 sector_rotation.analyze, 供 monkeypatch."""
    from a_stock.sector_rotation import analyze
    try:
        return analyze()
    except Exception:
        return None


class SectorMomentum(BaseStrategy):
    META = StrategyMeta("sector_momentum", 0.5, "板块动量: 主线确立+候选涨>3%")

    def filter(self, code, name):
        return build_indicators(code) is not None

    def signals(self, code, name):
        sr = _analyze()
        if not sr or getattr(sr, "verdict", "") != "持续主线":
            return []
        ind = build_indicators(code)
        if ind["change_pct"] > 3:
            return [Signal(code, name, "buy", 0.5, "sector_momentum",
                           f"主线{sr.strongest_repeat_name} 候选涨{ind['change_pct']:.1f}%",
                           {"price": ind["last_close"],
                            "main_sector": sr.strongest_repeat_name})]
        return []
