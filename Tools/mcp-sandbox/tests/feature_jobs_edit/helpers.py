# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ.setdefault("SANDBOX_HOST_WORKSPACE", str(ROOT / ".test_workspace"))


# Clear task_root children and return the task_root path.
def reset_task_root():
    from sandbox import workspace

    task_root = workspace.task_root()
    task_root.mkdir(parents=True, exist_ok=True)
    for child in list(task_root.iterdir()):
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        except PermissionError:
            pass
    return task_root
