# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


PKG_ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = PKG_ROOT / "supervisor"
SRC = PKG_ROOT / "src"

for path in (SUPERVISOR, SRC):
    entry = str(path)
    if entry not in sys.path:
        sys.path.insert(0, entry)

os.environ.setdefault("SANDBOX_HOST_WORKSPACE", str(PKG_ROOT))


@pytest.fixture(autouse=True)
def _sandbox_host_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANDBOX_HOST_WORKSPACE", str(PKG_ROOT))
