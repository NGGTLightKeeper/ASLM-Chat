# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import importlib.util
import sys
from pathlib import Path


# Shared config path setup.
_SHARED_CONFIG = Path(__file__).resolve().parents[2] / "config.py"
if not _SHARED_CONFIG.exists():
    raise ImportError(f"Shared config file not found: {_SHARED_CONFIG}")


# Shared config module loading.
_spec = importlib.util.spec_from_file_location("_mcp_web_search_config", _SHARED_CONFIG)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Failed to load shared config module from {_SHARED_CONFIG}")

_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)


# Public symbol export.
for _name in dir(_module):
    if _name.startswith("_"):
        continue
    globals()[_name] = getattr(_module, _name)

__all__ = [name for name in globals() if not name.startswith("_")]
