# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import io
import json
import re
import sys
from pathlib import Path

# Force UTF-8 stdout.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Make the project root importable.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


# Write success JSON (html, url, title, inner_text) to stdout.
def _ok(
    html: str,
    url: str,
    title: str,
    inner_text: str = "",
    *,
    payload_kind: str = "html",
) -> None:
    sys.stdout.write(
        json.dumps(
            {
                "ok": True,
                "html": html,
                "url": url,
                "title": title,
                "method": "camoufox",
                "inner_text": inner_text,
                "payload_kind": payload_kind,
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    sys.stdout.flush()


# Write error JSON to stdout.
def _fail(msg: str) -> None:
    sys.stdout.write(json.dumps({"ok": False, "error": msg}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# Parse <title> from HTML for the worker response.
def _extract_title(html: str) -> str:
    m = _TITLE_RE.search(html)
    if m:
        import html as html_lib
        return html_lib.unescape(m.group(1)).strip()[:500]
    return ""


import random  # noqa: E402 (after sys.path setup)

_UA_POOL = {
    "windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    ],
    "macos": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.6; rv:124.0) Gecko/20100101 Firefox/124.0",
    ],
    "linux": [
        "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    ],
}
_SCREEN_POOL = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
]
_TZ_BY_LOCALE = {
    "en-US": ["America/New_York", "America/Chicago", "America/Los_Angeles"],
    "en-GB": ["Europe/London"],
    "de-DE": ["Europe/Berlin"],
}
_PLATFORM_BY_OS = {"windows": "Win32", "macos": "MacIntel", "linux": "Linux x86_64"}
_OS_WEIGHTS = [("windows", 0.70), ("macos", 0.20), ("linux", 0.10)]


# Weighted random OS for browser fingerprint rotation.
def _pick_os() -> str:
    keys = [k for k, _ in _OS_WEIGHTS]
    weights = [w for _, w in _OS_WEIGHTS]
    return random.choices(keys, weights=weights, k=1)[0]


# Build locale-specific Camoufox browser profile dict.
def _build_profile(locale: str) -> dict:
    os_name = _pick_os()
    tz_pool = _TZ_BY_LOCALE.get(locale, ["UTC"])
    return {
        "os": os_name,
        "locale": locale,
        "timezone": random.choice(tz_pool),
        "screen": dict(random.choice(_SCREEN_POOL)),
        "user_agent": random.choice(_UA_POOL.get(os_name, _UA_POOL["windows"])),
        "platform": _PLATFORM_BY_OS.get(os_name, "Win32"),
    }


# Apply navigator and viewport overrides on the Playwright page.
async def _apply_profile(page, profile: dict) -> None:
    init_script = (
        "Object.defineProperty(navigator, 'language', {get: () => '%s'});"
        "Object.defineProperty(navigator, 'languages', {get: () => ['%s', 'en']});"
        "Object.defineProperty(navigator, 'platform', {get: () => '%s'});"
    ) % (profile["locale"], profile["locale"], profile["platform"])
    try:
        await page.add_init_script(init_script)
    except Exception:
        pass
    try:
        await page.set_extra_http_headers({
            "Accept-Language": f"{profile['locale']},en;q=0.7",
            "User-Agent": profile["user_agent"],
        })
    except Exception:
        pass
    try:
        await page.set_viewport_size(profile["screen"])
    except Exception:
        pass


# Scroll the page partially to mimic human reading behavior.
async def _human_scroll(page) -> None:
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.25)")
        await asyncio.sleep(random.uniform(0.3, 0.8))
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.6)")
        await asyncio.sleep(random.uniform(0.2, 0.6))
    except Exception:
        pass


# Visit warmup URLs before the target to build a natural session.
async def _warmup(page, warmup_urls: list[str], count: int, timeout_sec: float) -> None:
    targets = random.sample(warmup_urls, min(count, len(warmup_urls))) if warmup_urls else []
    for wu in targets:
        try:
            await page.goto(wu, timeout=int(timeout_sec * 500), wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(0.5, 1.2))
            await _human_scroll(page)
        except Exception:
            continue


# Load url in Camoufox and emit HTML JSON on stdout.
async def _fetch(payload: dict) -> None:
    url: str = payload.get("url", "")
    if not url:
        _fail("empty url")
        return

    wait_sec: float = float(payload.get("wait_sec", 4.0))
    headless: bool = bool(payload.get("headless", True))
    humanize: bool = bool(payload.get("humanize", True))
    geoip: bool = bool(payload.get("geoip", False))
    locale: str = str(payload.get("locale", "en-US"))
    proxy = payload.get("proxy") or None
    warmup_urls: list = list(payload.get("warmup_urls") or ["https://www.wikipedia.org/"])
    warmup_count: int = int(payload.get("warmup_count", 1))
    timeout_sec: float = float(payload.get("timeout_sec", 45.0))
    fetch_json_from_page: bool = bool(payload.get("fetch_json_from_page"))
    json_query: str = str(payload.get("json_query") or "")

    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError as exc:
        _fail(f"camoufox not installed: {exc}")
        return

    profile = _build_profile(locale)
    launch_kwargs: dict = {
        "headless": headless,
        "humanize": humanize,
        "geoip": geoip,
        "locale": profile["locale"],
    }
    if proxy:
        launch_kwargs["proxy"] = proxy

    try:
        async with AsyncCamoufox(**launch_kwargs) as browser:
            page = await browser.new_page()
            await _apply_profile(page, profile)
            await _warmup(page, warmup_urls, warmup_count, timeout_sec)

            await page.goto(
                url,
                timeout=int(timeout_sec * 1000),
                wait_until="domcontentloaded" if fetch_json_from_page else "load",
            )
            if fetch_json_from_page:
                try:
                    await page.wait_for_function(
                        "document.body && document.body.innerText.trim().length > 80",
                        timeout=int(wait_sec * 1000),
                    )
                except Exception:
                    await asyncio.sleep(min(wait_sec, 2.0))

                body_text = ""
                try:
                    body_text = await page.evaluate("document.body.innerText") or ""
                except Exception:
                    pass
                if "blocked by network security" in body_text.lower():
                    _fail(f"antibot wall on thread page {url}")
                    return

                json_text = await page.evaluate(
                    """async (query) => {
                        const path = window.location.pathname.replace(/\\/$/, '') + '.json';
                        const target = query ? `${path}?${query}` : path;
                        const resp = await fetch(target, {
                            credentials: 'include',
                            headers: { 'Accept': 'application/json' },
                        });
                        if (!resp.ok) return '';
                        return await resp.text();
                    }""",
                    json_query,
                )
                json_text = (json_text or "").strip()
                if not json_text or not json_text.startswith("["):
                    _fail(f"empty or invalid reddit json from in-page fetch for {url}")
                    return
                _ok(json_text, url=url, title="", inner_text=json_text, payload_kind="json")
                return

            try:
                await page.wait_for_function(
                    "document.body.innerText.trim().length > 500",
                    timeout=int(wait_sec * 1000),
                )
            except Exception:
                await asyncio.sleep(min(wait_sec, 2.0))
            await _human_scroll(page)

            html = await page.content()
            if not html or len(html) < 200:
                _fail(f"empty page content from {url}")
                return

            inner_text = ""
            try:
                inner_text = await page.evaluate("document.body.innerText") or ""
            except Exception:
                pass

            title = _extract_title(html)
            _ok(html=html, url=url, title=title, inner_text=inner_text)

    except asyncio.TimeoutError:
        _fail(f"timeout after {timeout_sec:.0f}s for {url}")
    except Exception as exc:
        _fail(f"camoufox error: {type(exc).__name__}: {exc}")


# stdin: JSON line; stdout: one JSON line with html or error.
def main() -> None:
    try:
        raw = sys.stdin.buffer.read()
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as exc:
        _fail(f"bad stdin: {exc}")
        sys.exit(1)

    try:
        asyncio.run(_fetch(payload))
    except Exception as exc:
        _fail(f"worker crash: {type(exc).__name__}: {exc}")

    import os as _os
    _os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _fail(f"worker crash: {exc}")
        import os as _os
        _os._exit(1)
