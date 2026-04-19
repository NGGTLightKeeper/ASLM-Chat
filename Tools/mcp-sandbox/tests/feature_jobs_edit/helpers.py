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


def reset_task_root():
    from sandbox import workspace
    from sandbox.session_state import reset_session_state

    reset_session_state()
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
