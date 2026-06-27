"""策略注册表: 目录反射扫描 (抄 KHunter strategy_registry.py:175-238 思路, 简化).
新增策略文件自动注册, 不用改这里."""
import importlib
import pkgutil
from .base import BaseStrategy

_REGISTRY: dict[str, BaseStrategy] = {}


def _auto_register() -> None:
    """扫描 strategies/ 目录, 注册所有 BaseStrategy 子类."""
    if _REGISTRY:
        return
    import a_stock.strategies as pkg
    for _, name, _ in pkgutil.iter_modules(pkg.__path__):
        if name.startswith("_") or name in ("base", "registry"):
            continue
        try:
            mod = importlib.import_module(f"a_stock.strategies.{name}")
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if (isinstance(obj, type)
                        and issubclass(obj, BaseStrategy)
                        and obj is not BaseStrategy
                        and obj.META is not None):
                    _REGISTRY[obj.META.id] = obj()
        except Exception as e:
            print(f"⚠ 策略 {name} 注册失败: {e}")


def get_all() -> dict[str, BaseStrategy]:
    _auto_register()
    return _REGISTRY


def get(strategy_id: str) -> BaseStrategy | None:
    _auto_register()
    return _REGISTRY.get(strategy_id)


def run_all(df: dict) -> list[dict]:
    """对单标的跑所有策略, 返回命中列表."""
    _auto_register()
    hits = []
    for sid, strat in _REGISTRY.items():
        try:
            if strat.filter(df):
                hits.append({
                    "strategy_id": sid,
                    "strategy_name": strat.name,
                    "score": strat.score(df),
                    "stop_loss_pct": strat.META.stop_loss_pct,
                    "max_hold_days": strat.META.max_hold_days,
                })
        except Exception as e:
            print(f"⚠ 策略 {sid} 执行失败: {e}")
    return hits
