"""策略模块: 策略=信号列组合 (抄 tickflow).
新增策略零成本: 组合已有信号列. 导出公共接口."""
from a_stock.strategies.signals import Signal, SignalVote, aggregate
from a_stock.strategies.runner import run_all, run_top, build_indicators
from a_stock.strategies.registry import get_all, get, list_strategies

__all__ = [
    "Signal", "SignalVote", "aggregate",
    "run_all", "run_top", "build_indicators",
    "get_all", "get", "list_strategies",
]
