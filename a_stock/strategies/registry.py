"""策略注册表: 目录反射扫描 (抄 KHunter registry 思路, 简化).
新增策略文件自动注册, 不用改这里. 跳过骨架模块 (base/registry/runner/signals)."""
import importlib
import pkgutil

from a_stock.strategies.base import BaseStrategy

_SKIP = {"base", "registry", "runner", "signals"}
_REGISTRY: dict[str, BaseStrategy] = {}
_scanned = False


def _scan() -> None:
    """扫描 strategies/ 下所有非下划线非骨架模块, 收集 BaseStrategy 子类实例."""
    global _scanned
    _REGISTRY.clear()
    import a_stock.strategies as pkg
    for _, modname, _ in pkgutil.iter_modules(pkg.__path__):
        if modname.startswith("_") or modname in _SKIP:
            continue
        try:
            mod = importlib.import_module(f"a_stock.strategies.{modname}")
        except Exception as e:
            print(f"⚠ 策略模块 {modname} 导入失败, 跳过: {e}")
            continue
        for attr in vars(mod).values():
            if (isinstance(attr, type) and issubclass(attr, BaseStrategy)
                    and attr is not BaseStrategy
                    and attr.__module__ == mod.__name__):
                inst = attr()
                _REGISTRY[inst.META.name] = inst
    _scanned = True


def get_all() -> list:
    if not _scanned:
        _scan()
    return list(_REGISTRY.values())


def get(name: str):
    if not _scanned:
        _scan()
    return _REGISTRY.get(name)


def list_strategies() -> list:
    if not _scanned:
        _scan()
    return list(_REGISTRY.keys())
