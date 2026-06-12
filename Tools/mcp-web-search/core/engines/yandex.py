# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from ..fetch.profiles import build_nav_headers, pick
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

# Languages Yandex's site-search widget accepts as the 'lang' argument.
_SUPPORTED_LANGS = frozenset(
    {"ru", "en", "be", "fr", "de", "id", "kk", "tt", "tr", "uk"}
)


# Yandex web parser using the site-search ("frame") widget endpoint.
#
# The main https://yandex.com/search/ SERP is captcha-gated for scripted clients.
# The /search/site/ widget endpoint is far more scrapeable and renders organic
# results with stable b-serp-item__* markup, which is what searxng relies on.
class YandexParser:
    name = "yandex"
    search_url = "https://yandex.com/search/site/"

    _BLOCK_MARKERS = ("showcaptcha", "smartcaptcha", "checkcaptcha", "robot check", "captcha")
    _EMPTY_MARKERS = ("nothing found", "there are no search results", "ничего не нашлось", "ничего не найдено")
    _VARIANTS = (
        ("serp_items", "li[class*='serp-item']"),
        ("organic_results", "li[data-cid]"),
    )

    # Build a Yandex site-search request with the fixed widget parameters.
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
        profile = pick()
        params = {
            "tmpl_version": "releases",
            "text": query,
            "web": "1",
            "frame": "1",
            "searchid": "3131712",
        }
        if language in _SUPPORTED_LANGS:
            params["lang"] = language
        if page > 1:
            params["p"] = str(page - 1)

        headers = build_nav_headers(
            profile,
            referer="https://yandex.com/",
            sec_fetch_site="same-origin",
        )
        cookies = {"yp": "1716337604.sp.family%3A0#1685406411.szm.1:1920x1080:1920x999"}
        return EngineRequest(
            method="GET",
            url=YandexParser.search_url,
            params=params,
            headers=headers,
            cookies=cookies,
            primp_target=profile.primp_target,
            primp_os=profile.primp_os,
        )

    # Parse a raw Yandex site-search HTML document into normalized results.
    def parse(self, document: str) -> EngineParseResult:
        lowered = document.lower()
        blocked = any(marker in lowered for marker in self._BLOCK_MARKERS)
        explicit_empty = any(marker in lowered for marker in self._EMPTY_MARKERS)

        tree = parse_html(document)
        variant, cards = first_cards(tree, self._VARIANTS)

        results: list[SearchResult] = []
        malformed = 0
        for card in cards:
            title = first_node_text(
                card,
                (
                    "h3.b-serp-item__title a.b-serp-item__title-link",
                    ".b-serp-item__title-link",
                    "h3",
                ),
            )
            href = first_attribute(
                card,
                (
                    "a.b-serp-item__title-link",
                    "h3 a",
                    "a",
                ),
                "href",
            )
            snippet = first_node_text(
                card,
                (
                    ".b-serp-item__content .b-serp-item__text",
                    ".b-serp-item__text",
                ),
            )
            if not title or not valid_http_url(href):
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
