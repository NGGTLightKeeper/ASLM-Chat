# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import random
from dataclasses import dataclass


# A complete browser identity used to build convincing request metadata.
#
# primp_target uses a bare family alias ("chrome" / "edge") rather than a pinned
# version. Pinned versions are fragile: an unknown "chrome_NNN" silently falls back
# to a random fingerprint, and primp's Rust-side warning cannot be captured reliably
# to detect it. A bare alias always resolves to primp's bundled latest fingerprint
# for that family, so every request gets a coherent, real browser TLS fingerprint.
# Diversity is provided at the header level (UA version, platform, locale); on a
# single IP that matters more than TLS rotation, since rate limits are per-IP.
@dataclass(frozen=True)
class BrowserProfile:
    name: str
    user_agent: str
    sec_ch_ua: str
    sec_ch_ua_platform: str
    sec_ch_ua_mobile: str
    accept_language: str
    primp_target: str
    primp_os: str
    accept: str = (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;"
        "q=0.8,application/signed-exchange;v=b3;q=0.7"
    )


# All known realistic browser profiles for rotation.
_PROFILES: list[BrowserProfile] = [
    BrowserProfile(
        name="chrome_131_win",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.6778.86 Safari/537.36"
        ),
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
        accept_language="en-US,en;q=0.9",
        primp_target="chrome",
        primp_os="windows",
    ),
    BrowserProfile(
        name="chrome_130_win",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.6723.117 Safari/537.36"
        ),
        sec_ch_ua='"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
        accept_language="en-US,en;q=0.9",
        primp_target="chrome",
        primp_os="windows",
    ),
    BrowserProfile(
        name="chrome_131_mac",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.6778.86 Safari/537.36"
        ),
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"macOS"',
        sec_ch_ua_mobile="?0",
        accept_language="en-US,en;q=0.9",
        primp_target="chrome",
        primp_os="macos",
    ),
    BrowserProfile(
        name="chrome_130_mac",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.6723.117 Safari/537.36"
        ),
        sec_ch_ua='"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
        sec_ch_ua_platform='"macOS"',
        sec_ch_ua_mobile="?0",
        accept_language="en-US,en;q=0.9",
        primp_target="chrome",
        primp_os="macos",
    ),
    BrowserProfile(
        name="edge_131_win",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.2903.51"
        ),
        sec_ch_ua='"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
        accept_language="en-US,en;q=0.9",
        primp_target="edge",
        primp_os="windows",
    ),
    BrowserProfile(
        name="chrome_130_win_ru",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.6723.117 Safari/537.36"
        ),
        sec_ch_ua='"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
        accept_language="ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        primp_target="chrome",
        primp_os="windows",
    ),
]


# Pick a random browser profile from the pool.
def pick() -> BrowserProfile:
    return random.choice(_PROFILES)


# Build the full header set for a navigation request using the given profile.
# sec_fetch_site should be "same-origin" when the referer matches the host.
def build_nav_headers(
    profile: BrowserProfile,
    *,
    referer: str | None = None,
    sec_fetch_site: str = "none",
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    headers: dict[str, str] = {
        "User-Agent": profile.user_agent,
        "Accept": profile.accept,
        "Accept-Language": profile.accept_language,
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Sec-CH-UA": profile.sec_ch_ua,
        "Sec-CH-UA-Mobile": profile.sec_ch_ua_mobile,
        "Sec-CH-UA-Platform": profile.sec_ch_ua_platform,
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": sec_fetch_site,
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }
    if referer:
        headers["Referer"] = referer
    if extra:
        headers.update(extra)
    return headers
