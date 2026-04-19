from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import reset_task_root  # noqa: E402


class FeatureJobsEditSmokeTests(unittest.TestCase):
    def test_imports_without_docker(self) -> None:
        task_root = reset_task_root()

        from sandbox import workspace
        from sandbox import container
        from sandbox.api import handle_tool

        self.assertTrue(task_root.exists())
        self.assertTrue(callable(handle_tool))
        self.assertTrue(callable(workspace.edit))
        self.assertTrue(callable(container.exec_bash))


if __name__ == "__main__":
    unittest.main()
