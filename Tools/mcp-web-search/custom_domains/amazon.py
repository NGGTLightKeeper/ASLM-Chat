from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from custom_domains.common import CHROME_BASIC_HEADERS, extract_title, extract_with_preferred_pipeline, looks_blocked


async def fetch_amazon_snapshot(url: str, timeout: float = 20.0) -> dict[str, Any]:
    started = time.perf_counter()
    import httpx

    async with httpx.AsyncClient(
        headers=CHROME_BASIC_HEADERS,
        timeout=timeout,
        follow_redirects=True,
        http2=True,
    ) as client:
        response = await client.get(url)

    html = response.text or ""
    title = extract_title(html)
    parsed = extract_with_preferred_pipeline(url, html, prefer_trafilatura=False)
    return {
        "source": "amazon",
        "url": url,
        "engine": "httpx",
        "ua_profile": "chrome_basic",
        "status": int(response.status_code),
        "final_url": str(response.url),
        "content_type": response.headers.get("content-type", ""),
        "title": title,
        "raw_html_chars": len(html),
        "blocked_like": looks_blocked(title, html),
        "duration_sec": round(time.perf_counter() - started, 3),
        **parsed,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the custom Amazon snapshot fetcher.")
    parser.add_argument("url")
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = asyncio.run(fetch_amazon_snapshot(args.url, timeout=args.timeout))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
