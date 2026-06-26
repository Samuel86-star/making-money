"""项目包根。同时提供 pytest 兼容 shim (py.path / py.error)。"""

import sys as _sys

# 模块级 __getattr__:当访问 py.path / py.error 时,惰性加载 _pytest 内部的
# _pytest._py.path / _pytest._py.error,使 pytest 的 LEGACY_PATH 正常工作。
def __getattr__(name):
    if name == "path":
        import _pytest._py.path as _path
        _sys.modules["py.path"] = _path
        return _path
    if name == "error":
        import _pytest._py.error as _error
        _sys.modules["py.error"] = _error
        return _error
    raise AttributeError(f"module 'py' has no attribute {name!r}")