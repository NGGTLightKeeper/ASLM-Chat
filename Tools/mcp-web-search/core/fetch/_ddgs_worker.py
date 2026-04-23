# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
_ddgs_worker.py — Isolated subprocess worker for async_ddgs_search().

Protocol
--------
stdin  : one JSON line — the request payload (see async_ddgs_search for schema)
stdout : one JSON line — {"ok": true, "results": [...]} | {"ok": false, "error": "..."}
stderr : ignored by caller

Running in a separate process means:
  - DDGS HTTP calls can be hard-killed via proc.kill() with no thread-safety concerns
  - A hung DDGS request doesn't block the main asyncio event loop
  - Router telemetry accumulates inside _ddgs_worker.py's own process; the parent
    updates its own router after deserialising results (via engine field on SearchResult)

Exit codes
----------
  0  normal (ok=true or ok=false with error message)
  1  startup failure (import error, bad JSON, etc.)
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Force UTF-8 stdout so JSON with non-ASCII is transmitted cleanly
# ---------------------------------------------------------------------------
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Path: make core/ importable when run as a script from any working directory
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _fail(msg: str) -> None:
    sys.stdout.write(json.dumps({"ok": False, "error": msg}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    # --- Read request payload ------------------------------------------------
    try:
        raw = sys.stdin.buffer.read()
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as exc:
        _fail(f"bad stdin: {exc}")
        sys.exit(1)

    query: str = payload.get("query", "")
    if not query:
        _fail("empty query")
        sys.exit(1)

    max_results: int        = int(payload.get("max_results", 10))
    query_type: str         = str(payload.get("query_type", "general"))
    query_types             = payload.get("query_types")  # list[str] | None
    lang: str               = str(payload.get("lang", "en"))
    timelimit               = payload.get("timelimit")    # str | None
    hedge_count: int        = int(payload.get("hedge_count", 2))

    # DDGSClient construction params
    proxies: list[str]        = list(payload.get("proxies") or [])
    cache_db                  = payload.get("cache_db")  # str | None
    cache_ttl: int            = int(payload.get("cache_ttl", 3600))
    proxy_cooldown: int       = int(payload.get("proxy_cooldown", 3600))
    request_delay: list       = payload.get("request_delay", [0.15, 0.6])
    timeout: int              = int(payload.get("timeout", 10))
    max_retries: int          = int(payload.get("max_retries", 2))

    # --- Import and run ------------------------------------------------------
    try:
        from core.fetch.ddgs_client import DDGSClient
        from core.fetch.engine_stats import Observation
    except Exception as exc:
        _fail(f"import error: {exc}")
        sys.exit(1)

    client = DDGSClient(
        proxies=proxies,
        cache_db=cache_db,
        cache_ttl=cache_ttl,
        proxy_cooldown=proxy_cooldown,
        request_delay=(float(request_delay[0]), float(request_delay[1])),
        timeout=timeout,
        max_retries=max_retries,
    )

    try:
        results = client.search_with_fallback(
            query=query,
            max_results=max_results,
            query_type=query_type,
            query_types=query_types,
            lang=lang,
            timelimit=timelimit,
            hedge_count=hedge_count,
        )
    except Exception as exc:
        _fail(f"search_with_fallback error: {exc}")
        return

    serialised = [
        {
            "url": r.url,
            "title": r.title,
            "snippet": r.snippet,
            "engine": r.engine,
            "trust_tier": r.trust_tier,
            "score": float(r.score or 0.0),
            "method_hint": r.method_hint,
        }
        for r in results
    ]
    out = json.dumps({"ok": True, "results": serialised}, ensure_ascii=False)
    sys.stdout.write(out + "\n")
    sys.stdout.flush()
    # Hard-exit: bypass Python's thread-join on process shutdown.
    # ThreadPoolExecutor threads from search_with_fallback (hedged search) are
    # non-daemon and keep running until their HTTP timeout fires.  We already
    # wrote the result, so there's no reason to wait for them.
    import os as _os
    _os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _fail(f"worker crash: {exc}")
        import os as _os
        _os._exit(1)
