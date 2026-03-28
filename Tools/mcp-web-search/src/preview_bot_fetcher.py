# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Tier 1 — Preview-bot UA probe.

Uses social-media bot User-Agent strings (Telegrambot, WhatsApp, Slackbot, etc.)
via curl_cffi to coax sites into returning lightweight OpenGraph / preview HTML
instead of a full SPA or anti-bot challenge page.

Many moderate-WAF sites whitelist these UAs because they need link previews to
render in messengers.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bot UA pool — rotated per-request to avoid fingerprinting a single bot
# ---------------------------------------------------------------------------

_BOT_USER_AGENTS: list[str] = [
    # Telegram
    "TelegramBot (like TwitterBot)",
    # WhatsApp
    "WhatsApp/2.23.20.0",
    # Slack
    "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
    # Discord
    "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
    # Twitter / X
    "Twitterbot/1.0",
    # Facebook
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    # LinkedIn
    "LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +http://www.linkedin.com)",
    # Skype
    "SkypeUriPreview Preview/0.5",
]


# ---------------------------------------------------------------------------
# HTML → plain-text (same lightweight strip as overdrive.py)
# ---------------------------------------------------------------------------

def _html_to_text(raw_html: str) -> str:
    raw = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", "", raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return re.sub(r"\s{2,}", "\n", re.sub(r"<[^>]+>", " ", raw)).strip()


# ---------------------------------------------------------------------------
# Validity check (mirrors overdrive._is_valid_text)
# ---------------------------------------------------------------------------

_BLOCK_MARKERS = (
    "access denied",
    "403 forbidden",
    "cloudflare",
    "just a moment",
    "checking your browser",
    "enable javascript",
)


def _is_valid_text(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) <= 150:
        return False
    lowered = stripped[:2000].lower()
    return not any(marker in lowered for marker in _BLOCK_MARKERS)


# ---------------------------------------------------------------------------
# Core fetcher
# ---------------------------------------------------------------------------

async def fetch_with_preview_bot(
    url: str,
    *,
    timeout: int = 15,
    ua: Optional[str] = None,
) -> str:
    """Fetch *url* using a random social-media bot User-Agent via curl_cffi.

    Returns stripped plain text on success, or empty string on failure.
    """
    from curl_cffi import requests as cffi_requests

    chosen_ua = ua or random.choice(_BOT_USER_AGENTS)
    loop = asyncio.get_running_loop()

    def _do():
        r = cffi_requests.get(
            url,
            impersonate="chrome124",
            timeout=timeout,
            headers={
                "User-Agent": chosen_ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        r.raise_for_status()
        return r.text

    try:
        raw = await loop.run_in_executor(None, _do)
        text = _html_to_text(raw)
        if _is_valid_text(text):
            logger.debug("preview_bot: success for %s (ua=%s, %d chars)", url, chosen_ua, len(text))
            return text
        logger.debug("preview_bot: invalid text for %s (ua=%s, %d chars)", url, chosen_ua, len(text))
        return ""
    except Exception as exc:
        logger.debug("preview_bot: failed for %s (ua=%s): %s", url, chosen_ua, exc)
        return ""


# ---------------------------------------------------------------------------
# Multi-UA probe — tries up to N different bot UAs until one succeeds
# ---------------------------------------------------------------------------

async def probe_with_preview_bots(
    url: str,
    *,
    timeout: int = 15,
    max_attempts: int = 3,
) -> str:
    """Try up to *max_attempts* different bot UAs for *url*.

    Returns the first valid text, or empty string if all fail.
    """
    pool = list(_BOT_USER_AGENTS)
    random.shuffle(pool)

    for ua in pool[:max_attempts]:
        text = await fetch_with_preview_bot(url, timeout=timeout, ua=ua)
        if text:
            return text
    return ""
