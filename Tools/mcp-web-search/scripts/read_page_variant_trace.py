from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict

from services.read_page import ReadPageService, _dns_variant_urls, _host


async def _run(url: str) -> None:
    service = ReadPageService()
    variants = _dns_variant_urls(url) if _host(url) == "dns-shop.ru" else [url]
    result, attempts = await service.read_with_trace(url)
    print("Read page variant probe")
    print(f"URL: {url}")
    print(f"Variants: {len(variants)}")
    for idx, variant in enumerate(variants, 1):
        print(f"  {idx}. {variant}")
    print("")
    if attempts:
        print("Attempts:")
        for idx, attempt in enumerate(attempts, 1):
            data = asdict(attempt)
            print(
                f"  {idx}. variant={data['variant']} fetch={data['fetch_method']} "
                f"markdown_len={data['markdown_length']} weak={data['weak']} winner={data['winner']}"
            )
            print(f"     url={data['url']}")
        print("")
    preview = (result or "").strip().replace("\n", " ")
    print(f"Output chars: {len(result or '')}")
    print(f"Preview: {preview[:300]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Trace read_page variant behavior.")
    parser.add_argument("url", help="URL to read and trace")
    args = parser.parse_args()
    asyncio.run(_run(args.url))


if __name__ == "__main__":
    main()
