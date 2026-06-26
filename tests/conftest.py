"""Pytest conftest: locate vendored deps from project .venv or pip vendor dirs.

Tries ``import requests`` first; if unavailable, searches known vendored pip
paths across multiple Python version prefixes.  Falls back to excluding the
test module that needs ``requests`` from collection.
"""
from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 0.  Prefer the project .venv site-packages for pandas / pyarrow / requests.
#     System python3 (with user-site pytest) runs the tests; runtime deps
#     live in the .venv and need to be on sys.path explicitly.
#
#     NOTE: If the .venv was built for a different Python major.minor
#     (e.g. .venv has Python 3.12 but tests run on 3.14), the .venv C
#     extensions will be incompatible.  We detect this by probing numpy
#     (a canary with .so files) and fall through to vendored pip if the
#     .venv's C extensions are unloadable.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_VENV_SP = _PROJECT_ROOT / ".venv" / "lib" / "python3.12" / "site-packages"
if _VENV_SP.is_dir() and str(_VENV_SP) not in sys.path:
    sys.path.insert(0, str(_VENV_SP))

# Probe whether the .venv's C extensions are loadable.  numpy is a
# reliable canary because it has compiled .so files that fail loudly
# when the Python version doesn't match.
_venv_compatible = True
if _VENV_SP.is_dir():
    import importlib

    try:
        importlib.import_module("numpy")
    except ModuleNotFoundError:
        pass  # numpy not installed in .venv — not a mismatch
    except ImportError:
        # numpy found but C extensions failed to load — version mismatch
        sys.path.remove(str(_VENV_SP))
        _venv_compatible = False

# ---------------------------------------------------------------------------
# 1.  Try the direct import first -- works when requests is normally installed.
# ---------------------------------------------------------------------------
try:
    import requests  # noqa: F401
except ImportError:
    # -------------------------------------------------------------------
    # 2.  Search well-known vendored-pip locations for any Python 3.x ver.
    # -------------------------------------------------------------------
    _VERSIONS = ("3.10", "3.11", "3.12", "3.13", "3.14")
    _BASES = (
        "/opt/homebrew/lib",             # macOS Homebrew
        "/usr/local/lib",                # macOS / universal Unix
        str(Path.home() / ".local/lib"),  # pip --user
    )

    _found = False
    for ver in _VERSIONS:
        for base in _BASES:
            candidate = Path(base) / f"python{ver}" / "site-packages" / "pip" / "_vendor"
            if candidate.is_dir() and str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
                _found = True
                break
        if _found:
            break

    if not _found:
        # Also try Debian / Ubuntu dist-packages
        for ver in _VERSIONS:
            candidate = Path(f"/usr/lib/python{ver}/dist-packages/pip/_vendor")
            if candidate.is_dir() and str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
                _found = True
                break

    if not _found:
        # ---------------------------------------------------------------
        # 3.  No vendored requests anywhere -- skip the module that needs it.
        # ---------------------------------------------------------------
        collect_ignore_glob = ["test_a_stock_data_common.py"]