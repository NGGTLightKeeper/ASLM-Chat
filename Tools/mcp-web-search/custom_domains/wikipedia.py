# Copyright NEXTGGTECH. Elastic License 2.0.

"""Read Wikipedia articles through the official MediaWiki Action API."""

from __future__ import annotations

import html
import json
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from core.extract.page_normalizer import normalize_page

from custom_domains.base import FetchContext, PageResult

_API_MAX_BYTES = 8 * 1024 * 1024
_API_UA = "ASLM-Chat/1.0 (https://github.com/NGGTLightKeeper/ASLM-Chat)"


# Return the canonical desktop Wikipedia host, or "" for non-Wikipedia hosts.
def _wikipedia_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if host.endswith(".m.wikipedia.org"):
        host = host.removesuffix(".m.wikipedia.org") + ".wikipedia.org"
    if not host.endswith(".wikipedia.org") or host == "wikipedia.org":
        return ""
    return host


# Convert an article URL into its API endpoint and parse parameters.
def _api_request(url: str) -> tuple[str, dict[str, str]] | None:
    host = _wikipedia_host(url)
    if not host:
        return None

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    title = ""
    if parsed.path.startswith("/wiki/"):
        title = unquote(parsed.path.removeprefix("/wiki/"))
    elif parsed.path.rstrip("/") == "/w/index.php":
        title = (query.get("title") or [""])[0]

    oldid = (query.get("oldid") or [""])[0]
    pageid = (query.get("curid") or [""])[0]
    params = {
        "action": "parse",
        "prop": "text",
        "redirects": "1",
        "disableeditsection": "1",
        "disablelimitreport": "1",
        "format": "json",
        "formatversion": "2",
    }
    if oldid.isdigit():
        params["oldid"] = oldid
    elif pageid.isdigit():
        params["pageid"] = pageid
    elif title:
        params["page"] = title
    else:
        return None
    return f"https://{host}/w/api.php", params


# Fetch a bounded JSON response; API bodies contain the complete rendered article HTML.
async def _api_get_json(endpoint: str, params: dict[str, str], timeout: float) -> Any:
    import httpx

    headers = {"User-Agent": _API_UA, "Api-User-Agent": _API_UA}
    chunks: list[bytes] = []
    total = 0
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", endpoint, params=params, headers=headers) as response:
            response.raise_for_status()
            declared = int(response.headers.get("content-length") or 0)
            if declared > _API_MAX_BYTES:
                raise ValueError(f"Wikipedia API response exceeds {_API_MAX_BYTES} bytes")
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > _API_MAX_BYTES:
                    raise ValueError(f"Wikipedia API response exceeds {_API_MAX_BYTES} bytes")
                chunks.append(chunk)
    return json.loads(b"".join(chunks))


# Turn API HTML into the same structured markdown used by the generic reader.
def _payload_to_markdown(url: str, payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    parsed = payload.get("parse")
    if not isinstance(parsed, dict):
        return ""
    title = str(parsed.get("title") or "").strip()
    article_html = parsed.get("text")
    if isinstance(article_html, dict):
        article_html = article_html.get("*")
    if not isinstance(article_html, str) or not article_html.strip():
        return ""
    document = (
        "<!doctype html><html><head><title>"
        + html.escape(title or url)
        + '</title><meta property="og:title" content="'
        + html.escape(title or url, quote=True)
        + '"></head><body><article>'
        + article_html
        + "</article></body></html>"
    )
    markdown = normalize_page(url, document, favor_recall=True)
    if title and markdown:
        lines = markdown.splitlines()
        if lines and lines[0].startswith("# "):
            lines[0] = f"# {title}"
            markdown = "\n".join(lines)
    return markdown


# Fetch and normalize one Wikipedia article.
async def fetch_wikipedia_page(url: str, timeout: float = 20.0) -> str:
    request = _api_request(url)
    if request is None:
        return f"Error: Unsupported Wikipedia URL: {url}"
    endpoint, params = request
    try:
        payload = await _api_get_json(endpoint, params, timeout)
    except Exception as exc:
        return f"Error: Wikipedia API fetch failed for {url}: {exc}"

    markdown = _payload_to_markdown(url, payload)
    if markdown:
        return markdown
    error = payload.get("error") if isinstance(payload, dict) else None
    detail = error.get("info") if isinstance(error, dict) else "empty API response"
    return f"Error: Wikipedia API parse failed for {url}: {detail}"


class WikipediaHandler:
    name = "wikipedia"
    fallback_to_generic = True

    def matches(self, url: str) -> bool:
        return _api_request(url) is not None

    async def read(self, url: str, ctx: FetchContext) -> PageResult:
        markdown = await fetch_wikipedia_page(url, timeout=ctx.timeout)
        ok = bool(markdown) and not markdown.lstrip().lower().startswith("error:")
        return PageResult(
            markdown=markdown,
            ok=ok,
            method="wikipedia_api",
            apply_budget=ok,
            error="" if ok else markdown,
        )


HANDLER = WikipediaHandler()

__all__ = ["HANDLER", "WikipediaHandler", "fetch_wikipedia_page"]
