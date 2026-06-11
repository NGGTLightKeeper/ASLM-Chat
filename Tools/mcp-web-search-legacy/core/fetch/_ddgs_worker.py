# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path

# Force UTF-8 stdout so JSON with non-ASCII is transmitted cleanly.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Keep stdout JSON-only; detailed engine timing diagnostics go to captured stderr.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    stream=sys.stderr,
)

# Make core/ importable when run as a script from any working directory.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# Write one JSON error line to stdout.
def _fail(msg: str) -> None:
    sys.stdout.write(json.dumps({"ok": False, "error": msg}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# stdin: JSON request; stdout: one JSON line with results or error.
def main() -> None:
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
    class_weights           = payload.get("class_weights")  # dict[str, float] | None
    lang: str               = str(payload.get("lang", "en"))
    timelimit               = payload.get("timelimit")    # str | None
    hedge_count: int        = int(payload.get("hedge_count", 2))
    routing_profile: str     = str(payload.get("routing_profile", "stability"))

    # DDGSClient construction params.
    proxies: list[str]        = list(payload.get("proxies") or [])
    cache_db                  = payload.get("cache_db")  # str | None
    cache_ttl: int            = int(payload.get("cache_ttl", 3600))
    proxy_cooldown: int       = int(payload.get("proxy_cooldown", 3600))
    request_delay: list       = payload.get("request_delay", [0.15, 0.6])
    timeout: int              = int(payload.get("timeout", 10))
    max_retries: int          = int(payload.get("max_retries", 2))
    partial_buffer_path       = payload.get("partial_buffer_path")

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
            class_weights=class_weights,
            lang=lang,
            timelimit=timelimit,
            hedge_count=hedge_count,
            routing_profile=routing_profile,
            partial_buffer_path=partial_buffer_path,
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
            "published_date": r.published_date,
            "consensus_votes": int(r.consensus_votes or 1),
            "consensus_engines": list(r.consensus_engines or []),
        }
        for r in results
    ]
    out = json.dumps({"ok": True, "results": serialised}, ensure_ascii=False)
    sys.stdout.write(out + "\n")
    sys.stdout.flush()
    # Hard-exit: bypass thread join on shutdown (hedged search may still be running).
    import os as _os
    _os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _fail(f"worker crash: {exc}")
        import os as _os
        _os._exit(1)
