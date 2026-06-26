"""Pytest conftest: add pip vendored requests to path for CI/pip-less env."""
import sys

_VENDOR = "/opt/homebrew/lib/python3.14/site-packages/pip/_vendor"
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)