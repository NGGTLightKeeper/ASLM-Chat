# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parent
for _p in (_ROOT / "supervisor", _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from sandbox.docker_host import pipe_to_container_supervisor


# Run the host-side stdio proxy for the in-container MCP supervisor.
def main() -> None:
    raise SystemExit(pipe_to_container_supervisor())


if __name__ == "__main__":
    main()
