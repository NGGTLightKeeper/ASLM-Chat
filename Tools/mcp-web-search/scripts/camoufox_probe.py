# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.fetch.camoufox_fetcher import fetch_with_camoufox, is_camoufox_available


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scripts/camoufox_probe.py",
        description="One-off Camoufox probe for a single URL.",
    )
    parser.add_argument("url", help="URL to fetch with Camoufox")
    parser.add_argument("--timeout", type=float, default=30.0, help="Camoufox page timeout in seconds")
    parser.add_argument("--wait", type=float, default=6.0, help="Extra wait after navigation in seconds")
    parser.add_argument("--save", action="store_true", help="Save full HTML/text dump into _out/camoufox_probe")
    return parser.parse_args()


async def _main() -> int:
    args = _parse_args()

    print(f"camoufox_available={is_camoufox_available()}")
    print(f"url={args.url}")
    print(f"timeout={args.timeout}s wait={args.wait}s")
    print()

    result = await fetch_with_camoufox(
        args.url,
        timeout_sec=args.timeout,
        process_timeout=args.timeout + 20.0,
        wait_sec=args.wait,
        warmup_count=0,
        normalize=True,
    )

    print(f"success={result.success}")
    print(f"method={result.method}")
    print(f"duration_sec={result.duration_sec:.2f}")
    print(f"title={result.title!r}")
    if result.error:
        print(f"error={result.error}")
    print(f"html_chars={len(result.html)}")
    print(f"text_chars={len(result.text)}")
    print()

    text_preview = (result.text or "").strip()
    html_preview = (result.html or "").strip()

    if text_preview:
        print("TEXT_PREVIEW:")
        print(text_preview[:4000])
        print()

    if html_preview:
        print("HTML_PREVIEW:")
        print(html_preview[:2500])
        print()

    if args.save:
        out_dir = REPO_ROOT / "_out" / "camoufox_probe"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "result"
        (out_dir / f"{safe_name}.txt").write_text(result.text or "", encoding="utf-8")
        (out_dir / f"{safe_name}.html").write_text(result.html or "", encoding="utf-8")
        (out_dir / f"{safe_name}.meta.txt").write_text(
            "\n".join(
                [
                    f"url={args.url}",
                    f"success={result.success}",
                    f"method={result.method}",
                    f"duration_sec={result.duration_sec:.2f}",
                    f"title={result.title}",
                    f"error={result.error}",
                    f"html_chars={len(result.html)}",
                    f"text_chars={len(result.text)}",
                ]
            ),
            encoding="utf-8",
        )
        print(f"saved_to={out_dir}")

    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
