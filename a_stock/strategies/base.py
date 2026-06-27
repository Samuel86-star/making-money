"""策略基类: META + filter + signals 三段式 (抄 tickflow builtin/*.py).
新增策略零成本: 组合已有信号列."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrategyMeta:
    id: str
    name: str
    params: dict = field(default_factory=dict)
    scoring: dict = field(default_factory=dict)  # {col: weight}
    stop_loss_pct: float = -0.08
    max_hold_days: int = 20


class BaseStrategy:
    """策略基类. 子类实现 filter() 返回布尔表达式/条件."""
    META: StrategyMeta = None

    def filter(self, df: dict) -> bool:
        """df: 单标的指标 dict. 返回是否命中."""
        raise NotImplementedError

    def score(self, df: dict) -> float:
        """命中后评分 0-100. 默认按 META.scoring 加权."""
        if not self.META or not self.META.scoring:
            return 50.0
        total = 0.0
        for col, weight in self.META.scoring.items():
            val = df.get(col, 0)
            if isinstance(val, (int, float)):
                total += val * weight
        return max(0, min(100, total))

    @property
    def name(self) -> str:
        return self.META.name if self.META else self.__class__.__name__


def limit_pct(code: str, name: str = "") -> float:
    """动态涨停价比例 (抄 tickflow near_limit_up.py:5).
    ST:5% / 创业板+科创:20% / 北交:30% / 主板:10%."""
    n = (name or "").upper()
    if "ST" in n:
        return 0.05
    if code.startswith(("300", "301", "688")):
        return 0.20
    if code.endswith(".BJ") or code.startswith(("8", "4")):
        return 0.30
    return 0.10
