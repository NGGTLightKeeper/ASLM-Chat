# Copyright NGGT.LightKeeper. All Rights Reserved.

"""Score (claim, evidence) pairs via stdin/stdout JSON for the Django server venv.

Usage (from mcp-web-search venv)::

    echo '{"claim":"...","sentences":["..."],"model_dir":null,"ttl_seconds":240}' \\
        | python -m core.query.gte_score_stdio
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    payload = json.load(sys.stdin)
    claim = str(payload.get("claim") or "")
    sentences = payload.get("sentences") or []
    if not isinstance(sentences, list):
        sentences = []
    model_dir_raw = payload.get("model_dir")
    model_dir = Path(model_dir_raw) if model_dir_raw else None
    ttl_seconds = float(payload.get("ttl_seconds") or 240.0)

    # Ensure GTE logs land in Tools/mcp-web-search/logs/gte.log
    try:
        from adapters.mcp.logging_setup import setup_logging

        setup_logging()
    except Exception:
        pass

    from core.query.gte_evidence_reranker import runtime

    scores = runtime.score_evidence(
        claim,
        [str(s) for s in sentences],
        model_dir=model_dir,
        ttl_seconds=ttl_seconds,
    )
    top = max((float(s) for s in scores), default=0.0)
    json.dump({"scores": scores, "topScore": top, "ok": True}, sys.stdout)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        json.dump({"ok": False, "error": str(exc), "scores": []}, sys.stdout)
        raise SystemExit(1) from exc
