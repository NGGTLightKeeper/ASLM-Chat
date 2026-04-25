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

from custom_domains.amazon import fetch_amazon_snapshot
from custom_domains.ebay import fetch_ebay_snapshot


def _read_test_records(path: str) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Expected JSON list")
    return [item for item in data if isinstance(item, dict) and item.get("url")]


def _pick_one_per_source(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen: dict[str, dict[str, Any]] = {}
    for item in records:
        source = str(item.get("source") or "").strip().lower()
        if source and source not in chosen:
            chosen[source] = item
    return list(chosen.values())


async def _run(input_path: str, output_path: str, timeout: float, wait: float) -> int:
    records = _pick_one_per_source(_read_test_records(input_path))
    rows: list[dict[str, Any]] = []

    for record in records:
        source = str(record.get("source") or "").strip().lower()
        url = str(record["url"])
        print(f"\n=== {source} ===")
        print(url)
        if source == "amazon":
            row = await fetch_amazon_snapshot(url, timeout=timeout)
        elif source == "ebay":
            row = await fetch_ebay_snapshot(url, timeout=timeout, wait=wait)
        else:
            continue
        rows.append({"record": record, "parsed": row})
        print(
            f"engine={row['engine']} blocked={row['blocked_like']} "
            f"raw_html_chars={row['raw_html_chars']} markdown_chars={row['markdown_chars']}"
        )
        print(f"title={row['title']!r}")

    payload = {
        "generated_at": time.time(),
        "input": input_path,
        "rows": rows,
    }
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved_to={out_path}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse one URL per retail source with the best currently known fetch path.",
    )
    parser.add_argument("--input", default="Tools/mcp-web-search/tmp/test_url.json")
    parser.add_argument("--out", default="Tools/mcp-web-search/tmp/best_retail_parse.json")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--wait", type=float, default=4.0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args.input, args.out, args.timeout, args.wait)))


if __name__ == "__main__":
    main()
