# Copyright NEXTGGTECH. Elastic License 2.0.

"""Hosted search-API keys (optional supplement layer).

Ported from the legacy `core/config/api_keys.py`, trimmed to the providers the new
pipeline actually wires (Tavily, Firecrawl, Brave, SerpApi) plus a few forward-compat
key slots. Keys live in `api_keys.json` next to this file; absent file or blank keys
mean the hosted layer is a no-op and search stays pure scrape. The example template is
copied in on first load so the shape is discoverable.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("services.web_search")

_API_KEYS_PATH = Path(__file__).parent / "api_keys.json"
_API_KEYS_EXAMPLE_PATH = Path(__file__).parent / "api_keys.json.example"


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


# Read a nullable string from a JSON dict (blank → None).
def _read_nullable_str(raw: dict, key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# Create api_keys.json from the example template when missing (best-effort).
def _bootstrap_api_keys_file(target: Path) -> None:
    if target.exists() or not _API_KEYS_EXAMPLE_PATH.is_file():
        return
    try:
        target.write_text(_API_KEYS_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info("Created api_keys.json from template at %s", target)
    except OSError as exc:
        logger.warning("Failed to create api_keys.json at %s: %s", target, exc)


# Load api_keys.json and cache an ApiKeysConfig singleton (custom path for tests only).
def load_api_keys(path: Path | None = None) -> ApiKeysConfig:
    global _cached_api_keys
    if _cached_api_keys is not None and path is None:
        return _cached_api_keys

    target = path or _API_KEYS_PATH
    _bootstrap_api_keys_file(target)
    try:
        raw = json.loads(target.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        config = ApiKeysConfig()
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Invalid/unreadable %s: %s — using empty key set", target, exc)
        config = ApiKeysConfig()
    else:
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
    return config


# Drop the cached config (tests that rewrite api_keys.json).
def reset_api_keys_cache() -> None:
    global _cached_api_keys
    _cached_api_keys = None
