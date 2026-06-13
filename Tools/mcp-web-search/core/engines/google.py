# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from ..fetch.profiles import build_nav_headers, for_engine
from .models import EngineParseResult, EngineRequest, SearchResult
from .parsing import (
    classify_parse,
    first_attribute,
    first_cards,
    first_node_text,
    parse_html,
    split_region,
    valid_http_url,
)

# SOCS cookie deliberately omitted — it triggers consent-gate redirects on some IPs.
_GOOGLE_COOKIES = {
    "CONSENT": "YES+",
}


# Unwrap a Google redirect URL to the actual destination URL.
def _unwrap_url(value: str) -> str:
    if value.startswith("/url?"):
        value = f"https://www.google.com{value}"
    parsed = urlparse(value)
    if parsed.netloc.endswith("google.com") and parsed.path == "/url":
        target = parse_qs(parsed.query).get("q", [""])[0]
        return unquote(target) if target else ""
    return value


# Return True when the URL points to a Google-owned domain.
def _is_internal(value: str) -> bool:
    host = urlparse(value).netloc.lower()
    return host.endswith("google.com") or host.endswith("googleusercontent.com")


# Google SERP parser with structural fallbacks and degradation reporting.
class GoogleParser:
    name = "google"
    # Engines sharing a provider family serve the same underlying index; consensus
    # voting counts one vote per family, not per engine.
    provider_family = "google"
    search_url = "https://www.google.com/search"

    _BLOCK_MARKERS = (
        "/sorry/",
        "unusual traffic",
        "our systems have detected",
        "/httpservice/retry/enablejs",
        "before you continue to google",
        "consent.google.com/save",
    )
    _EMPTY_MARKERS = ("did not match any documents", "no results found for")
    _VARIANTS = (
        ("result_containers", "div.MjjYud, div.Gx5Zad"),
        ("title_anchors", "a[href]:has(h3)"),
    )

    # Build the HTTP request for a Google search query using a random browser profile.
    @staticmethod
    def build_request(
        query: str,
        *,
        region: str = "us-en",
        safesearch: str = "moderate",
        timelimit: str | None = None,
        page: int = 1,
    ) -> EngineRequest:
        country, language = split_region(region)
        profile = for_engine("google")
        params = {
            "q": query,
            "num": "3",
            "filter": "0",
            "safe": {"on": "high", "moderate": "medium", "off": "off"}.get(safesearch, "medium"),
            "start": str(max(0, page - 1) * 10),
            "ie": "utf8",
            "oe": "utf8",
            "hl": f"{language}-{country.upper()}",
            "lr": f"lang_{language}",
            "cr": f"country{country.upper()}",
        }
        if timelimit:
            params["tbs"] = f"qdr:{timelimit}"

        # Sec-Fetch-Site=same-origin because we're pretending to search from google.com.
        headers = build_nav_headers(
            profile,
            referer="https://www.google.com/",
            sec_fetch_site="same-origin",
            extra={"Accept-Language": f"{language}-{country.upper()},{language};q=0.9"},
        )
        return EngineRequest(
            method="GET",
            url=GoogleParser.search_url,
            params=params,
            headers=headers,
            cookies=_GOOGLE_COOKIES,
            primp_target=profile.primp_target,
            primp_os=profile.primp_os,
        )

    # Parse a raw Google SERP HTML document into an EngineParseResult.
    def parse(self, document: str) -> EngineParseResult:
        lowered = document.lower()
        blocked = any(marker in lowered for marker in self._BLOCK_MARKERS)
        explicit_empty = any(marker in lowered for marker in self._EMPTY_MARKERS)

        tree = parse_html(document)
        variant, cards = first_cards(tree, self._VARIANTS)

        results: list[SearchResult] = []
        malformed = 0
        for card in cards:
            title = first_node_text(card, ("h3",))
            href = first_attribute(card, (":scope", "a:has(h3)"), "href")
            href = _unwrap_url(href)
            snippet = first_node_text(
                card,
                (
                    ".VwiC3b",
                    ".yXK7lf",
                    "div[data-sncf]",
                ),
            )
            if not title or not valid_http_url(href) or _is_internal(href):
                malformed += 1
                continue
            results.append(SearchResult(title=title, url=href, snippet=snippet))

        return classify_parse(
            engine=self.name,
            results=results,
            parser_variant=variant,
            cards_seen=len(cards),
            malformed_cards=malformed,
            blocked=blocked and not results,
            explicit_empty=explicit_empty,
        )
