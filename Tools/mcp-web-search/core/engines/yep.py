# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import urlparse

from ..fetch.profiles import accept_language_for, build_nav_headers, for_engine
from .models import EngineParseResult, EngineRequest, ParseStatus, SearchResult
from .parsing import split_region

_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Yep safesearch level expected by the API.
_SAFESEARCH = {"off": "off", "moderate": "moderate", "on": "strict"}


# Yep parser backed by Yep's independent web index (JSON API).
#
# Yep returns a two-element JSON array; the second element holds the result set
# under 'results'. Snippets contain highlight markup that is stripped to text.
class YepParser:
    name = "yep"
    provider_family = "yep"
    search_url = "https://api.yep.com/search"

    # Build a Yep API request for the requested language and safe-search level.
    @staticmethod
    def build_request(
        query: str,
        *,
        region: str = "us-en",
        safesearch: str = "moderate",
        timelimit: str | None = None,
        page: int = 1,
    ) -> EngineRequest:
        _, language = split_region(region)
        profile = for_engine("yep")
        params = {
            "query": query,
            "safeSearch": _SAFESEARCH.get(safesearch, "moderate"),
            "limit": "20",
            "hl": language,
        }
        extra = {
            "Accept": "application/json",
            "Origin": "https://yep.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
        }
        accept_language = accept_language_for(language)
        if accept_language:
            extra["Accept-Language"] = accept_language
        headers = build_nav_headers(
            profile,
            referer="https://yep.com/",
            sec_fetch_site="same-site",
            extra=extra,
        )
        return EngineRequest(
            method="GET",
            url=YepParser.search_url,
            params=params,
            headers=headers,
            primp_target=profile.primp_target,
            primp_os=profile.primp_os,
        )

    # Parse Yep's JSON response and strip highlight markup from snippets.
    def parse(self, document: str) -> EngineParseResult:
        try:
            payload = json.loads(document)
        except json.JSONDecodeError as exc:
            return EngineParseResult(
                engine=self.name,
                status=ParseStatus.CHANGED,
                diagnostics=[f"Invalid JSON response: {exc}"],
            )

        # Expected shape: [meta, {"results": [...]}]. Anything else means the API
        # contract changed, which must surface as CHANGED rather than a silent empty.
        if not (isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], dict)):
            return EngineParseResult(
                engine=self.name,
                status=ParseStatus.CHANGED,
                diagnostics=["Unexpected Yep response shape (expected [meta, {results}])."],
            )

        items = payload[1].get("results") or []
        results: list[SearchResult] = []
        malformed = 0
        for item in items:
            if not isinstance(item, dict) or item.get("type") not in (None, "Organic"):
                continue
            title = str(item.get("title") or "").strip()
            href = str(item.get("url") or "").strip()
            raw_snippet = str(item.get("snippet") or "")
            snippet = " ".join(unescape(_HTML_TAG_RE.sub(" ", raw_snippet)).split())
            parsed = urlparse(href)
            if not title or parsed.scheme not in {"http", "https"} or not parsed.netloc:
                malformed += 1
                continue
            results.append(SearchResult(title=title, url=href, snippet=snippet))

        status = ParseStatus.SUCCESS if results else ParseStatus.EMPTY
        if results and malformed:
            status = ParseStatus.PARTIAL
        return EngineParseResult(
            engine=self.name,
            status=status,
            results=results,
            parser_variant="json_results",
            cards_seen=len(items),
            malformed_cards=malformed,
        )
