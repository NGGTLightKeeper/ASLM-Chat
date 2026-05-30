# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("config.api_keys")

_API_KEYS_PATH = Path(__file__).parent / "api_keys.json"
_API_KEYS_EXAMPLE_PATH = Path(__file__).parent / "api_keys.json.example"


@dataclass
class HostedSearchApiKeysSection:
    tavily_api_key: str | None = None
    brave_api_key: str | None = None
    serpapi_api_key: str | None = None
    serper_api_key: str | None = None
    exa_api_key: str | None = None
    kagi_api_key: str | None = None
    bing_api_key: str | None = None
    google_custom_search_api_key: str | None = None
    google_custom_search_cx: str | None = None
    yandex_api_key: str | None = None


@dataclass
class SearchApiKeysSection:
    hosted_api: HostedSearchApiKeysSection = field(default_factory=HostedSearchApiKeysSection)

    # Backward-compatible shortcuts for the previous flat field layout.
    @property
    def tavily_api_key(self) -> str | None:
        return self.hosted_api.tavily_api_key

    @property
    def brave_api_key(self) -> str | None:
        return self.hosted_api.brave_api_key

    @property
    def serpapi_api_key(self) -> str | None:
        return self.hosted_api.serpapi_api_key

    @property
    def serper_api_key(self) -> str | None:
        return self.hosted_api.serper_api_key

    @property
    def exa_api_key(self) -> str | None:
        return self.hosted_api.exa_api_key

    @property
    def kagi_api_key(self) -> str | None:
        return self.hosted_api.kagi_api_key

    @property
    def bing_api_key(self) -> str | None:
        return self.hosted_api.bing_api_key

    @property
    def google_custom_search_api_key(self) -> str | None:
        return self.hosted_api.google_custom_search_api_key

    @property
    def google_custom_search_cx(self) -> str | None:
        return self.hosted_api.google_custom_search_cx

    @property
    def yandex_api_key(self) -> str | None:
        return self.hosted_api.yandex_api_key


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


# Create api_keys.json from the example template when missing.
def _bootstrap_api_keys_file(target: Path) -> None:
    if target.exists():
        return
    if not _API_KEYS_EXAMPLE_PATH.is_file():
        return

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_API_KEYS_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info("Created api_keys.json from template at %s", target)
    except OSError as exc:
        logger.warning("Failed to create api_keys.json from template at %s: %s", target, exc)


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
        logger.info("api_keys.json not found at %s - using empty key set", target)
        config = ApiKeysConfig()
        if path is None:
            _cached_api_keys = config
        return config
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in %s: %s - using empty key set", target, exc)
        config = ApiKeysConfig()
        if path is None:
            _cached_api_keys = config
        return config

    search = raw.get("search", {})
    hosted_api = search.get("hosted_api", search)

    config = ApiKeysConfig(
        search=SearchApiKeysSection(
            hosted_api=HostedSearchApiKeysSection(
                tavily_api_key=_read_nullable_str(hosted_api, "tavily_api_key"),
                brave_api_key=_read_nullable_str(hosted_api, "brave_api_key"),
                serpapi_api_key=_read_nullable_str(hosted_api, "serpapi_api_key"),
                serper_api_key=_read_nullable_str(hosted_api, "serper_api_key"),
                exa_api_key=_read_nullable_str(hosted_api, "exa_api_key"),
                kagi_api_key=_read_nullable_str(hosted_api, "kagi_api_key"),
                bing_api_key=_read_nullable_str(hosted_api, "bing_api_key"),
                google_custom_search_api_key=_read_nullable_str(hosted_api, "google_custom_search_api_key"),
                google_custom_search_cx=_read_nullable_str(hosted_api, "google_custom_search_cx"),
                yandex_api_key=_read_nullable_str(hosted_api, "yandex_api_key"),
            ),
        )
    )

    if path is None:
        _cached_api_keys = config
    return config
