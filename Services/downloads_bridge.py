# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

# Bridge configuration
BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "Data" / "downloads_bridge_cache"
DETAIL_CACHE_DIR = CACHE_DIR / "ollama_details"
DETAIL_HTML_CACHE_DIR = CACHE_DIR / "ollama_detail_html"
SEARCH_CACHE_DIR = CACHE_DIR / "ollama_search"
REQUEST_TIMEOUT_SECONDS = 20

OLLAMA_SEARCH_URL = "https://ollama.com/search"
OLLAMA_CATEGORY_ID = "ollama-library"
OLLAMA_CATEGORY_TITLE = "Ollama Models"
OLLAMA_CATEGORY_DESCRIPTION = "Models published in the official Ollama library."
OLLAMA_GROUP_KEY = "ollama-models"
OLLAMA_TARGET_REF = "ollama_models"
PROTOCOL_VERSION = 1

DEFAULT_SORT_KEY = "popular"
SORT_FILTER_PREFIX = "sort:"
CAPABILITY_FILTER_PREFIX = "capability:"


# Search query model
# Store normalized Ollama search arguments
@dataclass(frozen=True)
class OllamaSearchQuery:
    """Represent a normalized Ollama search request."""

    query_text: str
    sort_key: str
    capabilities: tuple[str, ...]


# Response helpers
# Build a standard bridge response payload
def _response(
    *,
    success: bool = True,
    categories: list[dict[str, Any]] | None = None,
    items: list[dict[str, Any]] | None = None,
    filters: list[dict[str, Any]] | None = None,
    item_detail: dict[str, Any] | None = None,
    install_manifest: dict[str, Any] | None = None,
    uninstall_manifest: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Return a response payload that matches the bridge contract."""

    payload: dict[str, Any] = {
        "protocolVersion": PROTOCOL_VERSION,
        "success": success,
        "warnings": warnings or [],
    }
    if categories is not None:
        payload["categories"] = categories
    if items is not None:
        payload["items"] = items
    if filters is not None:
        payload["filters"] = filters
    if item_detail is not None:
        payload["itemDetail"] = item_detail
    if install_manifest is not None:
        payload["installManifest"] = install_manifest
    if uninstall_manifest is not None:
        payload["uninstallManifest"] = uninstall_manifest
    if error:
        payload["error"] = error
    return payload


# Request helpers
# Read and validate the JSON request from stdin
def _read_request() -> dict[str, Any]:
    """Return the bridge request payload or an empty dict."""

    raw_payload = sys.stdin.read().strip()
    if not raw_payload:
        return {}

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}

    return payload if isinstance(payload, dict) else {}


# Text normalization helpers
# Normalize text into a single readable line
def _normalize_text(value: str | None) -> str:
    """Collapse whitespace and normalize non-breaking spaces."""

    return " ".join(str(value or "").replace("\xa0", " ").split())


# Normalize bullet-style separators into the bridge format
def _normalize_separator(value: str) -> str:
    """Convert visual separators into pipe-delimited text."""

    normalized = str(value or "").replace("\u00b7", "|").replace("\u2022", "|")
    return " | ".join(part.strip() for part in normalized.split("|") if part.strip())


# Normalize a filter key for comparisons
def _normalize_filter_key(value: str | None) -> str:
    """Return a lowercase filter key."""

    return _normalize_text(value).lower()


# Remove duplicates while keeping the first occurrence
def _deduplicate_preserving_order(values: list[str]) -> list[str]:
    """Return unique values in their original order."""

    seen: set[str] = set()
    deduplicated: list[str] = []

    for value in values:
        normalized = _normalize_text(value)
        if not normalized:
            continue

        identity = normalized.lower()
        if identity in seen:
            continue

        seen.add(identity)
        deduplicated.append(normalized)

    return deduplicated


# Parse an integer from mixed text
def _parse_int(value: str) -> int:
    """Extract digits from text and return them as an integer."""

    digits = re.sub(r"[^0-9]", "", _normalize_text(value))
    return int(digits) if digits else 0


# Cache helpers
# Ensure that all cache directories exist
def _ensure_cache_dirs() -> None:
    """Create cache directories used by the bridge."""

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DETAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DETAIL_HTML_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SEARCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)


# Read a JSON cache payload
def _read_cache(path: Path) -> Any | None:
    """Read a JSON cache file and return its payload."""

    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# Write a JSON cache payload
def _write_cache(path: Path, payload: Any) -> None:
    """Write a JSON payload to the cache."""

    _ensure_cache_dirs()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# Write a plain text cache file
def _write_text_file(path: Path, content: str) -> None:
    """Write plain text content to disk."""

    _ensure_cache_dirs()
    path.write_text(content, encoding="utf-8")


# Resource key helpers
# Build a resource key for a model variant
def _variant_resource_key(slug: str, tag: str) -> str:
    """Return a normalized resource key for an Ollama variant."""

    normalized_tag = _normalize_text(tag)
    return f"ollama:{slug}:{normalized_tag}" if normalized_tag else f"ollama:{slug}"


# Extract the slug portion from a resource key
def _resource_key_to_slug(resource_key: str) -> str:
    """Return the slug part from a bridge resource key."""

    normalized = str(resource_key or "").strip()
    if normalized.startswith("ollama:"):
        return normalized.partition(":")[2].strip()
    return normalized


# Cache path helpers
# Resolve the JSON detail cache path for a slug
def _detail_cache_path(slug: str) -> Path:
    """Return the cache path for model detail JSON."""

    safe_slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", slug)
    return DETAIL_CACHE_DIR / f"{safe_slug}.json"


# Resolve the HTML detail cache path for a rendered block
def _detail_html_cache_path(slug: str, block_id: str, html_document: str) -> Path:
    """Return the cache path for a rendered HTML block."""

    safe_slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", slug)
    safe_block_id = re.sub(r"[^a-zA-Z0-9._-]+", "_", block_id)
    digest = hashlib.sha256(html_document.encode("utf-8")).hexdigest()[:16]
    return DETAIL_HTML_CACHE_DIR / f"{safe_slug}_{safe_block_id}_{digest}.html"


# URL helpers
# Resolve the Ollama page path for a model slug
def _resolve_model_page_path(slug: str) -> str:
    """Return the relative Ollama page path for a slug."""

    normalized_slug = _normalize_text(slug).strip("/")
    if not normalized_slug:
        return "/library"

    return f"/{normalized_slug}" if "/" in normalized_slug else f"/library/{normalized_slug}"


# Resolve the absolute Ollama page URL for a model slug
def _resolve_model_page_url(slug: str) -> str:
    """Return the absolute Ollama page URL for a slug."""

    return f"https://ollama.com{_resolve_model_page_path(slug)}"


# Build the cache path for a search query
def _search_cache_path(search_query: OllamaSearchQuery) -> Path:
    """Return the cache path for a search payload."""

    identity = json.dumps(
        {
            "q": search_query.query_text,
            "sort": search_query.sort_key,
            "capabilities": list(search_query.capabilities),
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return SEARCH_CACHE_DIR / f"{digest}.json"


# HTTP helpers
# Request text content from a remote page
def _request_text(url: str, params: list[tuple[str, str]] | None = None) -> str:
    """Fetch page content from Ollama."""

    import requests

    response = requests.get(
        url,
        params=params or None,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "ASLM-Chat Downloads Bridge"},
    )
    response.raise_for_status()
    return response.text


# Build a BeautifulSoup parser lazily so metadata-only bridge calls stay cheap.
def _make_soup(markup: str) -> Any:
    """Return a BeautifulSoup parser for one HTML fragment."""

    from bs4 import BeautifulSoup

    return BeautifulSoup(markup, "html.parser")


# Resolve a relative URL against the current page
def _absolutize_url(candidate: str | None, base_url: str) -> str:
    """Return an absolute URL or an empty string."""

    normalized = _normalize_text(candidate)
    return urljoin(base_url, normalized) if normalized else ""


# Payload formatting helpers
# Build a standard item detail line
def _build_detail_line(pull_count: str, tag_count: str, updated_text: str) -> str:
    """Join item metadata into a single detail string."""

    return " | ".join(part for part in (pull_count, tag_count, updated_text) if part)


# Build a standard variant detail line
def _build_variant_line(parts: list[str]) -> str:
    """Join variant metadata into a single detail string."""

    return " | ".join(part for part in parts if part)


# Build the static Ollama category payload
def _build_ollama_category() -> dict[str, Any]:
    """Return the bridge category metadata for Ollama."""

    return {
        "id": OLLAMA_CATEGORY_ID,
        "title": OLLAMA_CATEGORY_TITLE,
        "description": OLLAMA_CATEGORY_DESCRIPTION,
        "groupKey": OLLAMA_GROUP_KEY,
        "targetRef": OLLAMA_TARGET_REF,
        "sortOrder": 10,
    }


# Build default Ollama filter payloads when live filter data is not available.
def _build_default_filter_payloads(search_query: OllamaSearchQuery) -> list[dict[str, Any]]:
    """Return a stable fallback filter list for cache-first catalog loads."""

    active_capabilities = set(search_query.capabilities)
    active_sort = search_query.sort_key or DEFAULT_SORT_KEY
    filters: list[dict[str, Any]] = [
        {
            "key": f"{SORT_FILTER_PREFIX}popular",
            "title": "Popular",
            "kind": "sort",
            "selected": active_sort == "popular",
            "sortOrder": 10,
        },
        {
            "key": f"{SORT_FILTER_PREFIX}newest",
            "title": "Newest",
            "kind": "sort",
            "selected": active_sort == "newest",
            "sortOrder": 11,
        },
    ]

    for index, capability in enumerate(("cloud", "embedding", "vision", "tools", "thinking")):
        filters.append(
            {
                "key": f"{CAPABILITY_FILTER_PREFIX}{capability}",
                "title": capability.title(),
                "kind": "capability",
                "selected": capability in active_capabilities,
                "sortOrder": 100 + index,
            }
        )

    return filters


# HTML rendering helpers
# Build a standalone HTML document for preview blocks
def _build_html_document(inner_html: str, page_url: str, title: str) -> str:
    """Wrap a content block in a styled HTML document."""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <base href="{page_url}">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #1c1c1e;
      --surface: #232326;
      --surface-strong: #2c2c2e;
      --border: #38383a;
      --text: #ffffff;
      --muted: rgba(235, 235, 245, 0.72);
      --link: #0a84ff;
    }}

    * {{
      box-sizing: border-box;
    }}

    html, body {{
      margin: 0;
      padding: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", "Open Sans", sans-serif;
      line-height: 1.58;
      font-size: 14px;
    }}

    body {{
      padding: 8px 12px 20px;
    }}

    .content {{
      max-width: none;
    }}

    h1, h2, h3, h4, h5, h6 {{
      color: var(--text);
      margin: 1.15em 0 0.55em;
      line-height: 1.22;
      font-weight: 700;
    }}

    h1:first-child, h2:first-child, h3:first-child {{
      margin-top: 0;
    }}

    p, ul, ol, blockquote, pre {{
      margin: 0 0 14px;
      color: var(--muted);
    }}

    strong, b {{
      color: var(--text);
    }}

    a {{
      color: var(--link);
      text-decoration: none;
    }}

    a:hover {{
      text-decoration: underline;
    }}

    code {{
      font-family: "Cascadia Code", "Consolas", monospace;
      font-size: 0.92em;
      background: var(--surface);
      color: var(--text);
      padding: 2px 6px;
      border-radius: 7px;
    }}

    pre {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 14px;
      overflow: auto;
      color: var(--text);
    }}

    pre code {{
      background: transparent;
      padding: 0;
      border-radius: 0;
    }}

    ul, ol {{
      padding-left: 22px;
    }}

    li {{
      margin: 6px 0;
      color: var(--muted);
    }}

    img {{
      display: block;
      max-width: 100%;
      height: auto;
      margin: 16px auto;
      border-radius: 14px;
    }}

    .table-wrap {{
      width: 100%;
      max-width: 100%;
      overflow-x: auto;
      overflow-y: hidden;
      margin: 16px 0;
      padding-bottom: 2px;
    }}

    table {{
      width: max-content !important;
      min-width: 0 !important;
      max-width: none !important;
      border-collapse: collapse;
      margin: 0;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      overflow: hidden;
      display: table !important;
    }}

    thead, tbody {{
      width: auto;
    }}

    th, td {{
      border-bottom: 1px solid var(--border);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
      color: var(--muted);
      font-size: 13px;
    }}

    th {{
      color: var(--text);
      background: var(--surface-strong);
      font-weight: 600;
    }}

    tr:last-child td {{
      border-bottom: 0;
    }}

    blockquote {{
      border-left: 3px solid var(--border);
      padding-left: 12px;
      color: var(--muted);
    }}

    hr {{
      border: 0;
      border-top: 1px solid var(--border);
      margin: 18px 0;
    }}
  </style>
</head>
<body>
  <div class="content">
    {inner_html}
  </div>
</body>
</html>"""


# Normalize and cache a rendered HTML block
def _create_html_block_file(slug: str, block_id: str, title: str, node_html: str, page_url: str) -> str:
    """Create a cached HTML file for a rendered detail block."""

    fragment = _make_soup(node_html)

    # Normalize media links so cached files keep working offline
    for node in fragment.select("[src]"):
        node["src"] = _absolutize_url(node.get("src"), page_url)

    for node in fragment.select("[href]"):
        href = _normalize_text(node.get("href"))
        if href.startswith("#"):
            node["href"] = page_url + href
        else:
            node["href"] = _absolutize_url(href, page_url)

    # Wrap raw tables to preserve layout inside the embedded preview
    for table in list(fragment.select("table")):
        parent_classes = table.parent.get("class", []) if table.parent else []
        if "table-wrap" in parent_classes:
            continue

        wrapper = fragment.new_tag("div", attrs={"class": "table-wrap"})
        table.wrap(wrapper)

    html_document = _build_html_document(fragment.decode_contents(), page_url, title)
    cache_path = _detail_html_cache_path(slug, block_id, html_document)

    if not cache_path.exists():
        _write_text_file(cache_path, html_document)

    return str(cache_path)


# Search query helpers
# Normalize query text and selected filters
def _normalize_search_query(query_text: str, filter_keys: list[str] | None) -> OllamaSearchQuery:
    """Normalize a search request into the internal query model."""

    normalized_query = _normalize_text(query_text)
    normalized_filters = [_normalize_filter_key(value) for value in filter_keys or [] if _normalize_filter_key(value)]

    sort_key = DEFAULT_SORT_KEY
    capabilities: list[str] = []

    # Split mixed filter keys into sort and capability groups
    for filter_key in normalized_filters:
        if filter_key.startswith(SORT_FILTER_PREFIX):
            candidate = filter_key.removeprefix(SORT_FILTER_PREFIX).strip()
            if candidate:
                sort_key = candidate
            continue

        if filter_key.startswith(CAPABILITY_FILTER_PREFIX):
            capability = filter_key.removeprefix(CAPABILITY_FILTER_PREFIX).strip()
            if capability and capability not in capabilities:
                capabilities.append(capability)

    capabilities.sort()
    return OllamaSearchQuery(
        query_text=normalized_query,
        sort_key=sort_key or DEFAULT_SORT_KEY,
        capabilities=tuple(capabilities),
    )


# Build Ollama search parameters from the normalized query
def _build_search_params(search_query: OllamaSearchQuery) -> list[tuple[str, str]]:
    """Convert a normalized query into Ollama request parameters."""

    params: list[tuple[str, str]] = []

    if search_query.query_text:
        params.append(("q", search_query.query_text))

    for capability in search_query.capabilities:
        params.append(("c", capability))

    if search_query.sort_key and search_query.sort_key != DEFAULT_SORT_KEY:
        params.append(("o", search_query.sort_key))

    return params


# Search parsing helpers
# Parse filter payloads from the Ollama search page
def _parse_filter_payloads(soup: BeautifulSoup, search_query: OllamaSearchQuery) -> list[dict[str, Any]]:
    """Extract available filters from the current search page."""

    payloads: list[dict[str, Any]] = []
    active_capabilities = set(search_query.capabilities)
    active_sort = search_query.sort_key or DEFAULT_SORT_KEY

    # Parse sort options from the primary desktop select first
    sort_options = soup.select("#desktop-sort-select option")
    if not sort_options:
        # Keep a generic fallback because Ollama has changed this control before
        sort_options = soup.select("select option")

    if sort_options:
        for index, option in enumerate(sort_options):
            value = _normalize_filter_key(option.get("value"))
            if not value:
                continue

            payloads.append(
                {
                    "key": f"{SORT_FILTER_PREFIX}{value}",
                    "title": _normalize_text(option.get_text(" ", strip=True)) or value.title(),
                    "kind": "sort",
                    "selected": value == active_sort,
                    "sortOrder": 10 + index,
                }
            )

    # Parse capability checkboxes exposed by the search UI
    for index, input_node in enumerate(soup.select("input[type='checkbox'][name='c'][value]")):
        value = _normalize_filter_key(input_node.get("value"))
        if not value:
            continue

        label = soup.select_one(f"label[for='{input_node.get('id', '')}']")
        title = _normalize_text(label.get_text(" ", strip=True) if label else value.title()) or value.title()

        payloads.append(
            {
                "key": f"{CAPABILITY_FILTER_PREFIX}{value}",
                "title": title,
                "kind": "capability",
                # Respect both the requested query and the page's own checked state
                "selected": value in active_capabilities or input_node.has_attr("checked"),
                "sortOrder": 100 + index,
            }
        )

    return payloads


# Parse model cards from the Ollama search page
def _parse_search_items(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Extract search result cards from the current page."""

    items: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    for index, list_item in enumerate(soup.select("li[x-test-model]")):
        # Resolve the card identity from its main link
        anchor = list_item.select_one("a[href]")
        if anchor is None:
            continue

        href = _normalize_text(anchor.get("href"))
        if not href.startswith("/"):
            continue

        if href.startswith("/library/"):
            slug = href.removeprefix("/library/").strip("/")
        else:
            slug = href.removeprefix("/").strip("/")

        # Deduplicate cards because the page can occasionally surface repeats
        if not slug or slug in seen_slugs:
            continue

        # Read the visible card content
        title_node = list_item.select_one("[x-test-search-response-title]")
        title = _normalize_text(title_node.get_text(" ", strip=True) if title_node else slug)

        header_container = anchor.find("div", attrs={"title": True})
        summary_node = header_container.find("p") if header_container else None
        summary = _normalize_text(summary_node.get_text(" ", strip=True) if summary_node else "")

        tag_container = anchor.select_one("div.flex.flex-col > div.flex.flex-wrap")
        tag_values = _deduplicate_preserving_order(
            [_normalize_text(node.get_text(" ", strip=True)) for node in tag_container.select("span")] if tag_container else []
        )

        pull_count_node = list_item.select_one("[x-test-pull-count]")
        tag_count_node = list_item.select_one("[x-test-tag-count]")
        updated_node = list_item.select_one("[x-test-updated]")

        pull_count_text = _normalize_text(pull_count_node.get_text(" ", strip=True) if pull_count_node else "")
        tag_count_text = _normalize_text(tag_count_node.get_text(" ", strip=True) if tag_count_node else "")
        updated_text = _normalize_text(updated_node.get_text(" ", strip=True) if updated_node else "")

        # Build the compact bridge card payload used by the ASLM catalog list
        items.append(
            {
                "resourceKey": f"ollama:{slug}",
                "categoryId": OLLAMA_CATEGORY_ID,
                "groupKey": OLLAMA_GROUP_KEY,
                "title": title or slug,
                "summary": summary,
                "provider": "Ollama",
                "version": "",
                "homepageUrl": f"https://ollama.com{href}",
                "detail": _build_detail_line(
                    f"{pull_count_text} Pulls" if pull_count_text else "",
                    f"{tag_count_text} Tags" if tag_count_text else "",
                    updated_text,
                ),
                "tags": tag_values,
                "variantCount": _parse_int(tag_count_text),
                "defaultVariantResourceKey": _variant_resource_key(slug, "latest"),
                "sortOrder": index,
            }
        )
        seen_slugs.add(slug)

    return items


# Load search results with cache fallback
def _load_search_payload(
    query_text: str,
    filter_keys: list[str] | None,
    prefer_cached: bool,
    force_refresh: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Load search items and filters, using cache when requested."""

    # Resolve the cache entry for the current search request
    search_query = _normalize_search_query(query_text, filter_keys)
    cache_path = _search_cache_path(search_query)
    cached = _read_cache(cache_path)

    # Serve the cached payload immediately when the caller requests it
    if cached and prefer_cached and not force_refresh:
        return list(cached.get("items", [])), list(cached.get("filters", [])), []

    # Keep cache-first catalog opens fast. If no real cache exists yet, ASLM's
    # background force-refresh pass will populate it from Ollama.
    if prefer_cached and not force_refresh:
        return [], _build_default_filter_payloads(search_query), []

    try:
        # Refresh the cache from the live Ollama search page
        html = _request_text(OLLAMA_SEARCH_URL, _build_search_params(search_query))
        soup = _make_soup(html)
        filters = _parse_filter_payloads(soup, search_query)
        items = _parse_search_items(soup)
        _write_cache(cache_path, {"items": items, "filters": filters})
        return items, filters, []
    except Exception as exc:
        # Fall back to the previous cache when live refresh fails
        if cached:
            return (
                list(cached.get("items", [])),
                list(cached.get("filters", [])),
                [f"Using cached Ollama search data: {exc}"],
            )
        raise


# Detail parsing helpers
# Parse available model variants from the model page
def _parse_variant_payloads(soup: BeautifulSoup, slug: str) -> list[dict[str, Any]]:
    """Extract variant payloads from an Ollama model page."""

    variants: list[dict[str, Any]] = []
    seen_models: set[str] = set()
    page_path = _resolve_model_page_path(slug)

    # Variant links reuse the model page path and append the tag after a colon
    prefix = f"{page_path}:"

    # Capture the mobile variant rows first because they include fallback metadata
    mobile_rows: dict[str, dict[str, str]] = {}
    for mobile_anchor in soup.find_all("a", href=True):
        href = str(mobile_anchor.get("href", "")).strip()
        if not href.startswith(prefix):
            continue

        css_classes = " ".join(str(css_class) for css_class in mobile_anchor.get("class", []))
        if "sm:hidden" not in css_classes:
            continue

        secondary_text = mobile_anchor.find("p", class_=lambda value: value and "text-neutral-500" in value)
        # The mobile row often keeps metadata that is omitted from the desktop grid
        detail_text = _normalize_separator(_normalize_text(secondary_text.get_text(" ", strip=True) if secondary_text else ""))
        segments = [segment.strip() for segment in detail_text.split("|") if segment.strip()]
        mobile_rows[href] = {
            "size": segments[0] if len(segments) > 0 else "",
            "context": segments[1] if len(segments) > 1 else "",
            "input": segments[2] if len(segments) > 2 else "",
            "updated": segments[3] if len(segments) > 3 else "",
        }

    # Parse the main grid and backfill missing fields from the mobile rows
    for row in soup.select("div.group.sm\\:grid"):
        anchor = row.find("a", href=lambda value: isinstance(value, str) and value.startswith(prefix))
        if anchor is None:
            continue

        href = str(anchor.get("href", "")).strip()
        model_name = href.removeprefix("/library/").lstrip("/") if href.startswith("/library/") else href.lstrip("/")
        # Skip duplicates when the same tag appears in multiple responsive containers
        if model_name in seen_models:
            continue

        tag = model_name.partition(":")[2].strip()
        columns = row.select("p.col-span-2")
        size_text = _normalize_text(columns[0].get_text(" ", strip=True) if len(columns) > 0 else "")
        context_text = _normalize_text(columns[1].get_text(" ", strip=True) if len(columns) > 1 else "")
        input_text = _normalize_text(columns[2].get_text(" ", strip=True) if len(columns) > 2 else "")

        mobile_row = mobile_rows.get(href, {})
        if not size_text:
            size_text = mobile_row.get("size", "")
        if not context_text:
            context_text = mobile_row.get("context", "")
        if not input_text:
            input_text = mobile_row.get("input", "")

        # Normalize variant metadata so every row follows the same detail format
        updated_text = mobile_row.get("updated", "")
        context_label = context_text
        if context_label and "context" not in context_label.lower():
            context_label = f"{context_label} context window"

        detail_segments = [size_text, context_label, input_text, updated_text]
        tags = [segment for segment in (size_text, context_text, input_text) if segment]
        summary = input_text if input_text else ""

        variants.append(
            {
                "resourceKey": _variant_resource_key(slug, tag),
                "title": tag or "latest",
                "summary": summary,
                "version": "",
                "detail": _build_variant_line(detail_segments),
                "homepageUrl": f"https://ollama.com{prefix}{tag}" if tag else f"https://ollama.com{page_path}",
                "tags": tags,
                "sortOrder": len(variants),
            }
        )
        seen_models.add(model_name)

    return variants


# Extract the raw markdown readme from the page
def _extract_readme_markdown(soup: BeautifulSoup) -> str:
    """Return markdown readme content when the page exposes it."""

    editor = soup.select_one("textarea#editor")
    if editor is None:
        return ""

    markdown = unescape(editor.get_text("\n", strip=False))
    lines = [line.rstrip() for line in markdown.splitlines()]
    return "\n".join(lines).strip()


# Extract and cache the rendered HTML readme block
def _extract_readme_html_file(slug: str, soup: BeautifulSoup, page_url: str) -> str:
    """Return a cached HTML file for the rendered readme block."""

    readme_node = soup.select_one("#readme #display") or soup.select_one("#display")
    if readme_node is None:
        return ""

    return _create_html_block_file(
        slug=slug,
        block_id="readme",
        title=f"{slug} Readme",
        node_html=readme_node.decode_contents(),
        page_url=page_url,
    )


# Parse full item details from the model page
def _parse_item_detail(slug: str, html: str) -> dict[str, Any]:
    """Build the bridge detail payload for a model page."""

    soup = _make_soup(html)
    page_url = _resolve_model_page_url(slug)

    # Read the primary page metadata
    title = _normalize_text(soup.title.get_text(" ", strip=True) if soup.title else slug)
    summary_node = soup.select_one("textarea#summary-textarea")
    summary = _normalize_text(summary_node.get_text(" ", strip=True) if summary_node else "")

    pull_count_node = soup.select_one("[x-test-pull-count]")
    updated_node = soup.select_one("[x-test-updated]")

    pull_count_text = _normalize_text(pull_count_node.get_text(" ", strip=True) if pull_count_node else "")
    updated_text = _normalize_text(updated_node.get_text(" ", strip=True) if updated_node else "")
    detail = _build_detail_line(f"{pull_count_text} Pulls" if pull_count_text else "", "", updated_text)

    # Resolve variants and the preferred default selection
    variants = _parse_variant_payloads(soup, slug)
    default_variant = next((variant["resourceKey"] for variant in variants if variant["resourceKey"].endswith(":latest")), "")

    if not default_variant and variants:
        default_variant = str(variants[0]["resourceKey"])

    # Prefer the rendered readme block because it matches the source page styling
    # Keep markdown as a fallback for pages that do not expose the rendered section
    readme_html_file = _extract_readme_html_file(slug, soup, page_url)
    readme = _extract_readme_markdown(soup)
    blocks: list[dict[str, Any]] = []

    if readme_html_file:
        blocks.append(
            {
                "id": "readme",
                "title": "Readme",
                "format": "html-file",
                "content": "",
                "contentUrl": readme_html_file,
                "sourceUrl": page_url,
                "sortOrder": 10,
            }
        )
    elif readme:
        blocks.append(
            {
                "id": "readme",
                "title": "Readme",
                "format": "markdown",
                "content": readme,
                "contentUrl": "",
                "sourceUrl": page_url,
                "sortOrder": 10,
            }
        )

    return {
        "resourceKey": f"ollama:{slug}",
        "categoryId": OLLAMA_CATEGORY_ID,
        "groupKey": OLLAMA_GROUP_KEY,
        "title": title or slug,
        "summary": summary,
        "provider": "Ollama",
        "version": "",
        "homepageUrl": page_url,
        "detail": detail,
        "tags": [],
        "defaultVariantResourceKey": default_variant,
        "variants": variants,
        "blocks": blocks,
    }


# Sanitize detail payloads loaded from cache or network
def _sanitize_detail_payload(detail: dict[str, Any]) -> dict[str, Any]:
    """Remove unsupported blocks from a detail payload."""

    normalized = dict(detail or {})
    blocks = normalized.get("blocks")
    if isinstance(blocks, list):
        # Older cached payloads may still contain blocks removed from the new UI
        normalized["blocks"] = [
            block for block in blocks
            if _normalize_filter_key((block or {}).get("id")) != "quick-start"
        ]

    return normalized


# Load detail payloads with cache fallback
def _load_item_detail(
    slug: str,
    prefer_cached: bool,
    force_refresh: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Load model details, using cache when requested."""

    # Resolve the cache entry for the requested model
    cache_path = _detail_cache_path(slug)
    cached = _read_cache(cache_path) if prefer_cached or not force_refresh else None

    # Serve sanitized cached details immediately when requested
    if cached and prefer_cached and not force_refresh:
        return _sanitize_detail_payload(dict(cached)), []

    try:
        # Refresh the cache from the live model page
        detail = _sanitize_detail_payload(_parse_item_detail(slug, _request_text(_resolve_model_page_url(slug))))

        _write_cache(cache_path, detail)
        return detail, []
    except Exception as exc:
        # Fall back to cached details when refresh fails
        if cached and prefer_cached:
            return dict(cached), [f"Using cached details for {slug}: {exc}"]
        raise


# Manifest builders
# Build an install manifest for a selected resource
def _build_install_manifest(resource_key: str) -> dict[str, Any]:
    """Return the install manifest for an Ollama resource."""

    model_name = _resource_key_to_slug(resource_key)
    if not model_name:
        raise ValueError("Missing resourceKey for resolve_install.")

    return {
        "resourceKey": f"ollama:{model_name}",
        "categoryId": OLLAMA_CATEGORY_ID,
        "title": model_name,
        "version": "",
        "targetRef": OLLAMA_TARGET_REF,
        "actions": [
            {
                "type": "ollama_pull",
                "title": f"Pull {model_name} from the Ollama library",
                "engineId": "ollama-service",
                "targetRef": OLLAMA_TARGET_REF,
                "model": model_name,
            }
        ],
    }


# Build an uninstall manifest for a selected resource
def _build_uninstall_manifest(resource_key: str) -> dict[str, Any]:
    """Return the uninstall manifest for an Ollama resource."""

    model_name = _resource_key_to_slug(resource_key)
    if not model_name:
        raise ValueError("Missing resourceKey for resolve_uninstall.")

    return {
        "resourceKey": f"ollama:{model_name}",
        "categoryId": OLLAMA_CATEGORY_ID,
        "title": model_name,
        "version": "",
        "targetRef": OLLAMA_TARGET_REF,
        "actions": [
            {
                "type": "ollama_remove",
                "title": f"Remove {model_name} from the local Ollama library",
                "engineId": "ollama-service",
                "targetRef": OLLAMA_TARGET_REF,
                "model": model_name,
            }
        ],
    }


# Bridge operation handlers
# Handle the list_categories operation
def _handle_list_categories() -> dict[str, Any]:
    """Return the supported download categories."""

    return _response(categories=[_build_ollama_category()])


# Handle the list_items operation
def _handle_list_items(
    category_id: str,
    query_text: str,
    filter_keys: list[str] | None,
    prefer_cached: bool,
    force_refresh: bool,
) -> dict[str, Any]:
    """Return catalog items for the requested category."""

    if category_id != OLLAMA_CATEGORY_ID:
        return _response(success=False, error=f"Unsupported categoryId: {category_id}")

    items, filters, warnings = _load_search_payload(query_text, filter_keys, prefer_cached, force_refresh)
    return _response(items=items, filters=filters, warnings=warnings)


# Handle the describe_item operation
def _handle_describe_item(
    category_id: str,
    resource_key: str,
    prefer_cached: bool,
    force_refresh: bool,
) -> dict[str, Any]:
    """Return detailed metadata for a single item."""

    if category_id != OLLAMA_CATEGORY_ID:
        return _response(success=False, error=f"Unsupported categoryId: {category_id}")

    slug = _resource_key_to_slug(resource_key).split(":", 1)[0].strip()
    if not slug:
        return _response(success=False, error="Missing resourceKey for describe_item.")

    item_detail, warnings = _load_item_detail(slug, prefer_cached, force_refresh)
    return _response(item_detail=item_detail, warnings=warnings)


# Handle the resolve_install operation
def _handle_resolve_install(category_id: str, resource_key: str) -> dict[str, Any]:
    """Return an install manifest for a selected item."""

    if category_id != OLLAMA_CATEGORY_ID:
        return _response(success=False, error=f"Unsupported categoryId: {category_id}")

    return _response(install_manifest=_build_install_manifest(resource_key))


# Handle the resolve_uninstall operation
def _handle_resolve_uninstall(category_id: str, resource_key: str) -> dict[str, Any]:
    """Return an uninstall manifest for a selected item."""

    if category_id != OLLAMA_CATEGORY_ID:
        return _response(success=False, error=f"Unsupported categoryId: {category_id}")

    return _response(uninstall_manifest=_build_uninstall_manifest(resource_key))


# Dispatch helpers
# Route a bridge request to the matching handler
def dispatch(request: dict[str, Any]) -> dict[str, Any]:
    """Dispatch the incoming request to a bridge handler."""

    # Normalize the incoming request fields first
    operation = _normalize_text(request.get("operation")).lower()
    category_id = _normalize_text(request.get("categoryId"))
    resource_key = _normalize_text(request.get("resourceKey"))
    query_text = _normalize_text(request.get("queryText"))
    raw_filters = request.get("filters") if isinstance(request.get("filters"), list) else []
    filter_keys = [_normalize_text(value) for value in raw_filters if _normalize_text(value)]
    prefer_cached = bool(request.get("preferCached"))
    force_refresh = bool(request.get("forceRefresh"))

    # Route the request explicitly so unsupported operations fail clearly
    if operation == "list_categories":
        return _handle_list_categories()
    if operation == "list_items":
        return _handle_list_items(category_id, query_text, filter_keys, prefer_cached, force_refresh)
    if operation == "describe_item":
        return _handle_describe_item(category_id, resource_key, prefer_cached, force_refresh)
    if operation == "resolve_install":
        return _handle_resolve_install(category_id, resource_key)
    if operation == "resolve_uninstall":
        return _handle_resolve_uninstall(category_id, resource_key)

    return _response(success=False, error=f"Unsupported downloads bridge operation: {operation or '<empty>'}")


# CLI entry point
# Execute the bridge in stdin/stdout mode
def run_cli() -> int:
    """Run the downloads bridge as a CLI process."""

    try:
        response = dispatch(_read_request())
    except Exception as exc:
        response = _response(success=False, error=str(exc))

    print(json.dumps(response, ensure_ascii=True))
    return 0
