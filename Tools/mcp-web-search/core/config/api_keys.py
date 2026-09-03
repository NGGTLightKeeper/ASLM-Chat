# Copyright NEXTGGTECH. Elastic License 2.0.

"""Hosted search-API keys loaded from the ASLM-Chat generated JSON config."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("services.web_search")

_API_KEYS_PATH = Path(__file__).parent / "api_keys.json"


# One nullable key slot per wired hosted provider. Content-bearing providers (Tavily,
# Firecrawl) return full page text; Brave/SerpApi return SERP rows. Deliberately no
# Serper/Kagi/Google-CSE/Yandex slots — they are redundant SERP backends and pure
# maintenance weight; the scrape engines already cover that.
@dataclass
class HostedSearchApiKeysSection:
    tavily_api_key: str | None = None
    firecrawl_api_key: str | None = None
    brave_api_key: str | None = None
    serpapi_api_key: str | None = None


@dataclass
class SearchApiKeysSection:
    hosted_api: HostedSearchApiKeysSection = field(default_factory=HostedSearchApiKeysSection)


@dataclass
class ApiKeysConfig:
    search: SearchApiKeysSection = field(default_factory=SearchApiKeysSection)


_cached_api_keys: ApiKeysConfig | None = None
_cached_api_keys_signature: tuple[int, int] | None = None


# Read a nullable string from a JSON dict (blank → None).
def _read_nullable_str(raw: dict, key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# Return a stable file signature for invalidating the default API-key cache.
def _api_keys_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


# Load api_keys.json and cache an ApiKeysConfig singleton (custom path for tests only).
def load_api_keys(path: Path | None = None) -> ApiKeysConfig:
    global _cached_api_keys, _cached_api_keys_signature

    target = path or _API_KEYS_PATH
    signature = _api_keys_signature(target)
    if _cached_api_keys is not None and path is None and signature == _cached_api_keys_signature:
        return _cached_api_keys

    try:
        raw = json.loads(target.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        config = ApiKeysConfig()
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Invalid/unreadable %s: %s — using empty key set", target, exc)
        config = ApiKeysConfig()
    else:
        if not isinstance(raw, dict):
            raw = {}
        search = raw.get("search", {})
        hosted = search.get("hosted_api", search) if isinstance(search, dict) else {}
        config = ApiKeysConfig(
            search=SearchApiKeysSection(
                hosted_api=HostedSearchApiKeysSection(
                    tavily_api_key=_read_nullable_str(hosted, "tavily_api_key"),
                    firecrawl_api_key=_read_nullable_str(hosted, "firecrawl_api_key"),
                    brave_api_key=_read_nullable_str(hosted, "brave_api_key"),
                    serpapi_api_key=_read_nullable_str(hosted, "serpapi_api_key"),
                ),
            )
        )

    if path is None:
        _cached_api_keys = config
        _cached_api_keys_signature = signature
    return config


# Drop the cached config (tests that rewrite api_keys.json).
def reset_api_keys_cache() -> None:
    global _cached_api_keys, _cached_api_keys_signature
    _cached_api_keys = None
    _cached_api_keys_signature = None
