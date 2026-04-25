from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.fetch.camoufox_fetcher import fetch_with_camoufox, is_camoufox_available
from scripts.retail_read_probe import build_variants as _base_build_variants


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_OG_DESC_RE = re.compile(
    r'<meta\s+(?:property|name)=["\']og:description["\']\s+content=["\'](.*?)["\']',
    re.IGNORECASE,
)
_DESC_RE = re.compile(
    r'<meta\s+(?:property|name)=["\']description["\']\s+content=["\'](.*?)["\']',
    re.IGNORECASE,
)
_PRICE_RE = re.compile(r"\b(?:\$|€|£|₽)\s?\d[\d,.\s]{1,16}|\b\d[\d,.\s]{1,16}\s?(?:usd|eur|gbp|rub|rur|₽)\b", re.IGNORECASE)
_RATING_RE = re.compile(r"\b\d(?:\.\d)?\s*(?:out of 5|из 5|stars?|star rating)\b", re.IGNORECASE)
_SPEC_RE = re.compile(r"\b(?:ssd|ram|gb|tb|inch|inches|hz|ips|oled|rtx|core i[3579]|ryzen)\b", re.IGNORECASE)

_UA_PROFILES: dict[str, dict[str, str]] = {
    "chrome_basic": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    },
    "chrome_full": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    },
    "mobile_safari": {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 "
            "Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    },
    "googlebot": {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    },
    "slackbot": {
        "User-Agent": "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
    },
}

_DEFAULT_ENGINES: tuple[str, ...] = (
    "httpx",
    "requests",
    "curl_cffi",
    "camoufox",
    "patchright",
    "seleniumbase",
)


def _trim_text(text: str, limit: int = 240) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    return compact[:limit]


def _extract_title_and_preview(html: str) -> tuple[str, str]:
    title_match = _TITLE_RE.search(html or "")
    og_desc_match = _OG_DESC_RE.search(html or "")
    desc_match = _DESC_RE.search(html or "")
    title = _trim_text(title_match.group(1) if title_match else "", 180)
    preview = ""
    for match in (og_desc_match, desc_match):
        if match:
            preview = _trim_text(match.group(1), 240)
            break
    return title, preview


def _detect_response_class(final_url: str, content_type: str, title: str, body: str, status: int) -> str:
    lower_url = (final_url or "").lower()
    lower_title = (title or "").lower()
    lower_body = (body or "").lower()
    ct = (content_type or "").lower()

    if "showcaptcha" in lower_url or "captcha" in lower_title or "smartcaptcha" in lower_body:
        return "captcha"
    if status in {401, 403} or "access denied" in lower_title:
        return "blocked"
    if status == 404 or "not found" in lower_title or "нет такой страницы" in lower_title:
        return "not_found"
    if "application/json" in ct:
        if '"type": "captcha"' in lower_body or '"type":"captcha"' in lower_body:
            return "json_captcha"
        return "json"
    if "xml" in ct and "html" not in ct:
        return "xml"
    if any(marker in lower_body for marker in ("product-osku", "priceoffer", "togglewishlist", "addtocartbutton")):
        return "html_product_like"
    if any(marker in lower_body for marker in ("shopping", "amazon", "ebay", "price")):
        return "html"
    return "unknown"


def _signal_summary(title: str, body: str) -> dict[str, bool]:
    hay = f"{title}\n{body}"
    return {
        "has_price": bool(_PRICE_RE.search(hay)),
        "has_rating": bool(_RATING_RE.search(hay)),
        "has_specs": bool(_SPEC_RE.search(hay)),
    }


def _score_result(result: dict[str, Any]) -> int:
    cls = result.get("response_class", "unknown")
    score = {
        "json": 100,
        "xml": 95,
        "html_product_like": 80,
        "html": 60,
        "unknown": 20,
        "not_found": 5,
        "blocked": 0,
        "captcha": -10,
        "json_captcha": -10,
    }.get(cls, 0)
    signals = result.get("signals", {})
    score += 5 * sum(1 for value in signals.values() if value)
    return score


def _read_test_urls(path: str) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Expected a JSON list of URL records")
    return [item for item in data if isinstance(item, dict) and item.get("url")]


def _extend_variants(url: str) -> list[dict[str, str]]:
    variants = _base_build_variants(url)
    base = url.split("?", 1)[0]
    extras = [
        {"kind": ".yml", "url": f"{base}.yml"},
        {"kind": "/.yml", "url": f"{base}/.yml"},
        {"kind": "?format=yml", "url": f"{base}?format=yml"},
        {"kind": "?output=yml", "url": f"{base}?output=yml"},
        {"kind": "/spec", "url": f"{base}/spec"},
        {"kind": "/specifications", "url": f"{base}/specifications"},
    ]
    seen = {item["url"] for item in variants}
    for item in extras:
        if item["url"] not in seen:
            variants.append(item)
            seen.add(item["url"])
    return variants


def _probe_httpx(url: str, timeout: float, headers: dict[str, str]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        import httpx

        with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True, http2=True) as client:
            response = client.get(url)
        text = response.text or ""
        title, preview = _extract_title_and_preview(text)
        result = {
            "engine": "httpx",
            "ok": 200 <= int(response.status_code) < 400,
            "status": int(response.status_code),
            "final_url": str(response.url),
            "content_type": response.headers.get("content-type", ""),
            "title": title,
            "preview": preview,
            "chars": len(text),
            "duration_sec": round(time.perf_counter() - started, 3),
            "error": "",
        }
        result["response_class"] = _detect_response_class(result["final_url"], result["content_type"], title, text, result["status"])
        result["signals"] = _signal_summary(title, text)
        return result
    except Exception as exc:
        return {
            "engine": "httpx",
            "ok": False,
            "status": 0,
            "final_url": url,
            "content_type": "",
            "title": "",
            "preview": "",
            "chars": 0,
            "duration_sec": round(time.perf_counter() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
            "response_class": "error",
            "signals": {"has_price": False, "has_rating": False, "has_specs": False},
        }


def _probe_requests(url: str, timeout: float, headers: dict[str, str]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        import requests

        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        text = response.text or ""
        title, preview = _extract_title_and_preview(text)
        result = {
            "engine": "requests",
            "ok": 200 <= int(response.status_code) < 400,
            "status": int(response.status_code),
            "final_url": str(response.url),
            "content_type": response.headers.get("content-type", ""),
            "title": title,
            "preview": preview,
            "chars": len(text),
            "duration_sec": round(time.perf_counter() - started, 3),
            "error": "",
        }
        result["response_class"] = _detect_response_class(result["final_url"], result["content_type"], title, text, result["status"])
        result["signals"] = _signal_summary(title, text)
        return result
    except Exception as exc:
        return {
            "engine": "requests",
            "ok": False,
            "status": 0,
            "final_url": url,
            "content_type": "",
            "title": "",
            "preview": "",
            "chars": 0,
            "duration_sec": round(time.perf_counter() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
            "response_class": "error",
            "signals": {"has_price": False, "has_rating": False, "has_specs": False},
        }


def _probe_curl_cffi(url: str, timeout: float, headers: dict[str, str]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        from curl_cffi import requests as cffi_req

        response = cffi_req.get(
            url,
            impersonate="chrome124",
            timeout=timeout,
            allow_redirects=True,
            headers=headers,
        )
        text = response.text or ""
        title, preview = _extract_title_and_preview(text)
        result = {
            "engine": "curl_cffi",
            "ok": 200 <= int(response.status_code) < 400,
            "status": int(response.status_code),
            "final_url": str(response.url),
            "content_type": response.headers.get("content-type", ""),
            "title": title,
            "preview": preview,
            "chars": len(text),
            "duration_sec": round(time.perf_counter() - started, 3),
            "error": "",
        }
        result["response_class"] = _detect_response_class(result["final_url"], result["content_type"], title, text, result["status"])
        result["signals"] = _signal_summary(title, text)
        return result
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
            "response_class": "error",
            "signals": {"has_price": False, "has_rating": False, "has_specs": False},
        }


async def _probe_camoufox(url: str, timeout: float, wait: float) -> dict[str, Any]:
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
            "response_class": "error",
            "signals": {"has_price": False, "has_rating": False, "has_specs": False},
        }

    try:
        fetch = await fetch_with_camoufox(
            url,
            timeout_sec=timeout,
            process_timeout=timeout + 20.0,
            wait_sec=wait,
            warmup_count=0,
            normalize=False,
        )
        text = fetch.html or fetch.text or ""
        title = _trim_text(fetch.title, 180)
        preview = _trim_text(text, 240)
        result = {
            "engine": "camoufox",
            "ok": bool(fetch.success),
            "status": 200 if fetch.success else 0,
            "final_url": fetch.url or url,
            "content_type": "",
            "title": title,
            "preview": preview,
            "chars": len(text),
            "duration_sec": round(time.perf_counter() - started, 3),
            "error": fetch.error or "",
        }
        result["response_class"] = _detect_response_class(result["final_url"], result["content_type"], title, text, result["status"])
        result["signals"] = _signal_summary(title, text)
        return result
    except Exception as exc:
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
            "error": f"{type(exc).__name__}: {exc}",
            "response_class": "error",
            "signals": {"has_price": False, "has_rating": False, "has_specs": False},
        }


async def _probe_patchright(url: str, timeout: float, wait: float, headers: dict[str, str]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        from patchright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=headers.get("User-Agent", ""),
                extra_http_headers={k: v for k, v in headers.items() if k.lower() != "user-agent"},
            )
            page = await context.new_page()
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
            await context.close()
            await browser.close()
        result = {
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
        result["response_class"] = _detect_response_class(final_url, content_type, title, html, int(status or 0))
        result["signals"] = _signal_summary(title, html)
        return result
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
            "response_class": "error",
            "signals": {"has_price": False, "has_rating": False, "has_specs": False},
        }


def _probe_seleniumbase(url: str, timeout: float, wait: float, headers: dict[str, str]) -> dict[str, Any]:
    started = time.perf_counter()
    driver = None
    try:
        from seleniumbase import Driver

        driver = Driver(
            browser="chrome",
            headless=True,
            uc=True,
            agent=headers.get("User-Agent", ""),
            incognito=True,
            do_not_track=True,
            disable_csp=True,
            page_load_strategy="eager",
        )
        driver.set_page_load_timeout(max(5, int(timeout)))
        driver.get(url)
        time.sleep(wait)
        html = driver.page_source or ""
        title = _trim_text(driver.get_title(), 180)
        final_url = driver.current_url
        preview = _trim_text(html, 240)
        result = {
            "engine": "seleniumbase",
            "ok": True,
            "status": 200,
            "final_url": final_url,
            "content_type": "",
            "title": title,
            "preview": preview,
            "chars": len(html),
            "duration_sec": round(time.perf_counter() - started, 3),
            "error": "",
        }
        result["response_class"] = _detect_response_class(final_url, "", title, html, 200)
        result["signals"] = _signal_summary(title, html)
        return result
    except Exception as exc:
        return {
            "engine": "seleniumbase",
            "ok": False,
            "status": 0,
            "final_url": url,
            "content_type": "",
            "title": "",
            "preview": "",
            "chars": 0,
            "duration_sec": round(time.perf_counter() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
            "response_class": "error",
            "signals": {"has_price": False, "has_rating": False, "has_specs": False},
        }
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


async def _run_engine(engine: str, url: str, timeout: float, wait: float, headers: dict[str, str]) -> dict[str, Any]:
    if engine == "httpx":
        return await asyncio.to_thread(_probe_httpx, url, timeout, headers)
    if engine == "requests":
        return await asyncio.to_thread(_probe_requests, url, timeout, headers)
    if engine == "curl_cffi":
        return await asyncio.to_thread(_probe_curl_cffi, url, timeout, headers)
    if engine == "camoufox":
        return await _probe_camoufox(url, timeout, wait)
    if engine == "patchright":
        return await _probe_patchright(url, timeout, wait, headers)
    if engine == "seleniumbase":
        return await asyncio.to_thread(_probe_seleniumbase, url, timeout, wait, headers)
    raise ValueError(f"Unknown engine: {engine}")


async def _stage1_suffix_probe(url: str, timeout: float, headers: dict[str, str], max_variants: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for variant in _extend_variants(url)[:max_variants]:
        result = await asyncio.to_thread(_probe_httpx, variant["url"], timeout, headers)
        rows.append({
            "kind": variant["kind"],
            "url": variant["url"],
            "probe": result,
        })
    return rows


def _pick_promising_variants(stage1_rows: list[dict[str, Any]], keep: int) -> list[dict[str, str]]:
    scored: list[tuple[int, dict[str, str]]] = []
    for row in stage1_rows:
        probe = row["probe"]
        result = {
            "kind": row["kind"],
            "url": row["url"],
        }
        scored.append((_score_result(probe), result))

    scored.sort(key=lambda item: item[0], reverse=True)
    kept: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, item in scored:
        if item["url"] in seen:
            continue
        kept.append(item)
        seen.add(item["url"])
        if len(kept) >= keep:
            break
    return kept


async def _stage2_ua_probe(
    variants: list[dict[str, str]],
    timeout: float,
    ua_profiles: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for variant in variants:
        for ua_name in ua_profiles:
            headers = dict(_UA_PROFILES[ua_name])
            result = await asyncio.to_thread(_probe_httpx, variant["url"], timeout, headers)
            rows.append({
                "kind": variant["kind"],
                "url": variant["url"],
                "ua_profile": ua_name,
                "probe": result,
            })
    return rows


def _pick_best_candidates(stage2_rows: list[dict[str, Any]], keep: int) -> list[dict[str, str]]:
    scored: list[tuple[int, dict[str, str]]] = []
    for row in stage2_rows:
        probe = row["probe"]
        candidate = {
            "kind": row["kind"],
            "url": row["url"],
            "ua_profile": row["ua_profile"],
        }
        scored.append((_score_result(probe), candidate))

    scored.sort(key=lambda item: item[0], reverse=True)
    kept: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for _, item in scored:
        key = (item["url"], item["ua_profile"])
        if key in seen:
            continue
        kept.append(item)
        seen.add(key)
        if len(kept) >= keep:
            break
    return kept


async def _stage3_engine_probe(
    candidates: list[dict[str, str]],
    timeout: float,
    wait: float,
    engines: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        headers = dict(_UA_PROFILES[candidate["ua_profile"]])
        for engine in engines:
            result = await _run_engine(engine, candidate["url"], timeout, wait, headers)
            rows.append({
                "kind": candidate["kind"],
                "url": candidate["url"],
                "ua_profile": candidate["ua_profile"],
                "engine": engine,
                "probe": result,
            })
    return rows


def _build_summary(stage3_rows: list[dict[str, Any]]) -> dict[str, Any]:
    best_row: dict[str, Any] | None = None
    best_score = -10**9
    for row in stage3_rows:
        score = _score_result(row["probe"])
        if score > best_score:
            best_score = score
            best_row = row
    return {
        "best_score": best_score,
        "best_path": best_row if best_row else {},
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scripts/retail_matrix_probe.py",
        description="Temporary matrix probe for suffixes, UA profiles, and multiple fetch engines.",
    )
    parser.add_argument(
        "--input",
        default="Tools/mcp-web-search/tmp/test_url.json",
        help="JSON file with URL records.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional limit of URL records to process.")
    parser.add_argument("--timeout", type=float, default=18.0, help="Per-request timeout in seconds.")
    parser.add_argument("--wait", type=float, default=3.0, help="Extra browser wait time in seconds.")
    parser.add_argument("--max-variants", type=int, default=12, help="How many suffix/query variants to test in stage 1.")
    parser.add_argument("--keep-variants", type=int, default=3, help="How many promising variants to carry into stage 2.")
    parser.add_argument("--keep-candidates", type=int, default=2, help="How many (variant + UA) candidates to carry into stage 3.")
    parser.add_argument(
        "--ua-profiles",
        default="chrome_basic,chrome_full,mobile_safari,googlebot,slackbot",
        help="Comma-separated UA profiles to use in stage 2/3.",
    )
    parser.add_argument(
        "--engines",
        default=",".join(_DEFAULT_ENGINES),
        help="Comma-separated engine list for stage 3.",
    )
    parser.add_argument("--out", default="", help="Optional JSON output path.")
    return parser.parse_args()


async def main() -> int:
    args = _parse_args()
    records = _read_test_urls(args.input)
    if args.limit > 0:
        records = records[: args.limit]

    ua_profiles = [item.strip() for item in args.ua_profiles.split(",") if item.strip()]
    unknown_profiles = [item for item in ua_profiles if item not in _UA_PROFILES]
    if unknown_profiles:
        raise SystemExit(f"Unknown UA profiles: {', '.join(unknown_profiles)}")

    engines = [item.strip() for item in args.engines.split(",") if item.strip()]
    report: dict[str, Any] = {
        "generated_at": time.time(),
        "input": args.input,
        "results": [],
    }

    stage1_headers = dict(_UA_PROFILES["chrome_full"])

    for index, record in enumerate(records, 1):
        url = str(record["url"])
        print(f"\n=== [{index}/{len(records)}] {record.get('source', '?')} {url}")
        stage1_rows = await _stage1_suffix_probe(url, timeout=args.timeout, headers=stage1_headers, max_variants=args.max_variants)
        promising_variants = _pick_promising_variants(stage1_rows, keep=args.keep_variants)
        print(f"stage1 tested={len(stage1_rows)} promising={len(promising_variants)}")

        stage2_rows = await _stage2_ua_probe(promising_variants, timeout=args.timeout, ua_profiles=ua_profiles)
        best_candidates = _pick_best_candidates(stage2_rows, keep=args.keep_candidates)
        print(f"stage2 tested={len(stage2_rows)} best_candidates={len(best_candidates)}")

        stage3_rows = await _stage3_engine_probe(best_candidates, timeout=args.timeout, wait=args.wait, engines=engines)
        summary = _build_summary(stage3_rows)
        best_path = summary.get("best_path", {})
        if best_path:
            print(
                "best:",
                f"engine={best_path.get('engine')}",
                f"ua={best_path.get('ua_profile')}",
                f"kind={best_path.get('kind')}",
                f"class={best_path.get('probe', {}).get('response_class')}",
                f"title={best_path.get('probe', {}).get('title', '')[:80]!r}",
            )

        report["results"].append(
            {
                "record": record,
                "stage1_suffix_probe": stage1_rows,
                "stage2_ua_probe": stage2_rows,
                "stage3_engine_probe": stage3_rows,
                "summary": summary,
            }
        )

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nsaved_to={out_path}")
    else:
        print("\nJSON_SUMMARY:")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
