"""策略基类: META + filter + signals 三段式 (抄 tickflow builtin).
新增策略零成本: 继承 BaseStrategy, 声明 META, 实现 filter/signals."""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from a_stock.strategies.signals import Signal


@dataclass
class StrategyMeta:
    name: str
    confidence: float
    description: str


class BaseStrategy(ABC):
    """三段式模板: filter 初筛 → signals 产信号. evaluate 模板方法兜底异常."""
    META: StrategyMeta  # 子类必须声明

    @abstractmethod
    def filter(self, code: str, name: str) -> bool:
        """初筛: 标的适不适合本策略."""

    @abstractmethod
    def signals(self, code: str, name: str) -> list:
        """产信号: 满足条件返回 Signal[], 否则空列表."""

    def evaluate(self, code: str, name: str) -> list:
        """模板方法: filter 通过才跑 signals, 异常兜底返回 []."""
        try:
            if not self.filter(code, name):
                return []
            return self.signals(code, name) or []
        except Exception:
            return []


def limit_pct(code: str) -> float:
    """涨停幅度 %. 创业板(300)/科创板(688) 20%, 主板(含ETF) 10%."""
    if code.startswith(("300", "688")):
        return 20.0
    return 10.0
