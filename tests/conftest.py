"""Pytest conftest: locate pip-vendored requests for CI/pip-less environments.

Tries ``import requests`` first; if unavailable, searches known vendored pip
paths across multiple Python version prefixes.  Falls back to excluding the
test module that needs ``requests`` from collection.
"""
from __future__ import annotations

import sys
from pathlib import Path

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