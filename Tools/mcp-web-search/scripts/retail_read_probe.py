# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.fetch.camoufox_fetcher import fetch_with_camoufox, is_camoufox_available


# Build the retail read probe CLI argument parser.
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scripts/retail_read_probe.py",
        description="Probe retail product pages through curl_cffi, camoufox, and patchright across URL variants.",
    )
    parser.add_argument("urls", nargs="+", help="Base product URLs to probe.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout in seconds.")
    parser.add_argument("--wait", type=float, default=5.0, help="Extra browser wait time for camoufox/patchright.")
    parser.add_argument("--out", default="", help="Optional output JSON path.")
    return parser.parse_args()


# Collapse whitespace and trim text to a display limit.
def _trim_text(text: str, limit: int = 240) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    return compact[:limit]


# Extract title and meta description preview from HTML.
def _extract_title_and_preview(html: str) -> tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.IGNORECASE | re.DOTALL)
    og_desc_match = re.search(
        r'<meta\s+(?:property|name)=["\']og:description["\']\s+content=["\'](.*?)["\']',
        html or "",
        re.IGNORECASE,
    )
    desc_match = re.search(
        r'<meta\s+(?:property|name)=["\']description["\']\s+content=["\'](.*?)["\']',
        html or "",
        re.IGNORECASE,
    )
    title = _trim_text(title_match.group(1) if title_match else "", 180)
    preview = ""
    for match in (og_desc_match, desc_match):
        if match:
            preview = _trim_text(match.group(1), 240)
            break
    return title, preview


# Insert a dns-shop product path segment after /product/.
def _swap_product_segment(url: str, segment: str) -> str:
    parts = urlsplit(url)
    path = parts.path
    if "/product/" in path:
        path = path.replace("/product/", f"/product/{segment}/", 1)
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


# Build URL variants (suffixes, query params, host tricks) for one product URL.
def build_variants(url: str) -> list[dict[str, str]]:
    parts = urlsplit(url)
    host = parts.netloc
    path = parts.path.rstrip("/")
    variants: list[dict[str, str]] = [{"kind": "original", "url": url}]

    suffixes = [
        (".xml", f"{path}.xml"),
        ("/.xml", f"{path}/.xml"),
        (".json", f"{path}.json"),
        ("/.json", f"{path}/.json"),
    ]
    for label, new_path in suffixes:
        variants.append({"kind": label, "url": urlunsplit((parts.scheme, host, new_path, parts.query, parts.fragment))})

    query_variants = [
        ("?output=xml", "output=xml"),
        ("?output=json", "output=json"),
        ("?format=xml", "format=xml"),
        ("?format=json", "format=json"),
    ]
    for label, query in query_variants:
        variants.append({"kind": label, "url": urlunsplit((parts.scheme, host, parts.path, query, parts.fragment))})

    if host.startswith("www."):
        bare_host = host[4:]
        variants.append({"kind": "bare-host", "url": urlunsplit((parts.scheme, bare_host, parts.path, parts.query, parts.fragment))})
        variants.append({"kind": "xml-prefix-host", "url": urlunsplit((parts.scheme, f"xml.{bare_host}", parts.path, parts.query, parts.fragment))})
    else:
        variants.append({"kind": "xml-prefix-host", "url": urlunsplit((parts.scheme, f"xml.{host}", parts.path, parts.query, parts.fragment))})

    if "dns-shop.ru" in host:
        for segment in ("characteristics", "opinion", "accessories", "service-rating", "similar-design", "analog"):
            variants.append({"kind": f"product/{segment}", "url": _swap_product_segment(url, segment)})

    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for item in variants:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        deduped.append(item)
    return deduped


# Fetch one variant with curl_cffi chrome impersonation.
def probe_curl_cffi(url: str, timeout: float) -> dict[str, object]:
    started = time.perf_counter()
    try:
        from curl_cffi import requests as cffi_req

        response = cffi_req.get(
            url,
            impersonate="chrome124",
            timeout=timeout,
            allow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            },
        )
        text = response.text or ""
        title, preview = _extract_title_and_preview(text)
        return {
            "engine": "curl_cffi",
            "ok": 200 <= int(response.status_code) < 400,
            "status": int(response.status_code),
            "final_url": str(response.url),
            "content_type": response.headers.get("content-type"),
            "title": title,
            "preview": preview,
            "chars": len(text),
            "duration_sec": round(time.perf_counter() - started, 3),
            "error": "",
        }
    except Exception as exc:
        return {
            "engine": "curl_cffi",
            "ok": False,
            "status": 0,
            "final_url": url,
            "content_type": "",
            "title": "",
            "preview": "",
            "chars": 0,
            "duration_sec": round(time.perf_counter() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }


# Fetch one variant with Camoufox browser automation.
async def probe_camoufox(url: str, timeout: float, wait: float) -> dict[str, object]:
    started = time.perf_counter()
    if not is_camoufox_available():
        return {
            "engine": "camoufox",
            "ok": False,
            "status": 0,
            "final_url": url,
            "content_type": "",
            "title": "",
            "preview": "",
            "chars": 0,
            "duration_sec": round(time.perf_counter() - started, 3),
            "error": "camoufox unavailable",
        }

    result = await fetch_with_camoufox(
        url,
        timeout_sec=timeout,
        process_timeout=timeout + 20.0,
        wait_sec=wait,
        warmup_count=0,
        normalize=False,
    )
    title = _trim_text(result.title, 180)
    preview = _trim_text(result.text or result.html, 240)
    return {
        "engine": "camoufox",
        "ok": bool(result.success),
        "status": 200 if result.success else 0,
        "final_url": result.url or url,
        "content_type": "",
        "title": title,
        "preview": preview,
        "chars": len(result.html or result.text or ""),
        "duration_sec": round(time.perf_counter() - started, 3),
        "error": result.error,
    }


# Fetch one variant with Patchright headless Chromium.
async def probe_patchright(url: str, timeout: float, wait: float) -> dict[str, object]:
    started = time.perf_counter()
    try:
        from patchright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            response = await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
            await page.wait_for_timeout(int(wait * 1000))
            html = await page.content()
            title = _trim_text(await page.title(), 180)
            preview = _trim_text(html, 240)
            final_url = page.url
            status = response.status if response else 0
            content_type = ""
            if response:
                try:
                    content_type = response.headers.get("content-type", "")
                except Exception:
                    content_type = ""
            await browser.close()
            return {
                "engine": "patchright",
                "ok": bool(status and 200 <= status < 400),
                "status": int(status or 0),
                "final_url": final_url,
                "content_type": content_type,
                "title": title,
                "preview": preview,
                "chars": len(html),
                "duration_sec": round(time.perf_counter() - started, 3),
                "error": "",
            }
    except Exception as exc:
        return {
            "engine": "patchright",
            "ok": False,
            "status": 0,
            "final_url": url,
            "content_type": "",
            "title": "",
            "preview": "",
            "chars": 0,
            "duration_sec": round(time.perf_counter() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }


# Run curl_cffi, camoufox, and patchright probes for one URL variant.
async def probe_variant(variant: dict[str, str], timeout: float, wait: float) -> dict[str, object]:
    url = variant["url"]
    curl_result = await asyncio.to_thread(probe_curl_cffi, url, timeout)
    camoufox_result = await probe_camoufox(url, timeout, wait)
    patchright_result = await probe_patchright(url, timeout, wait)
    return {
        "kind": variant["kind"],
        "url": url,
        "results": [curl_result, camoufox_result, patchright_result],
    }


# CLI entry: probe all variants for each base URL and emit JSON summary.
async def main() -> int:
    args = _parse_args()
    all_rows: list[dict[str, object]] = []
    for base_url in args.urls:
        variants = build_variants(base_url)
        print(f"\n=== BASE {base_url} ===")
        print(f"variants={len(variants)} timeout={args.timeout}s wait={args.wait}s")
        rows: list[dict[str, object]] = []
        for variant in variants:
            row = await probe_variant(variant, args.timeout, args.wait)
            rows.append(row)
            print(f"[{variant['kind']}] {variant['url']}")
            for result in row["results"]:
                print(
                    f"  - {result['engine']:<10} ok={result['ok']!s:<5} "
                    f"status={result['status']:<4} chars={result['chars']:<7} "
                    f"title={result['title']!r} error={result['error']!r}"
                )
        all_rows.append({"base_url": base_url, "variants": rows})

    payload = {"generated_at": time.time(), "rows": all_rows}
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nsaved_to={out_path}")
    else:
        print("\nJSON_SUMMARY:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
