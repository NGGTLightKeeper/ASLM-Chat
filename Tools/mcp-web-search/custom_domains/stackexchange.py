# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from core.fetch.stackexchange_fetcher import fetch_stackexchange_question, is_stackexchange_question_url

from custom_domains.base import FetchContext, PageResult

__all__ = [
    "HANDLER",
    "StackExchangeHandler",
    "fetch_stackexchange_question",
    "is_stackexchange_question_url",
]


# Unified handler: fetch a Stack Exchange question + top answers via the API.
class StackExchangeHandler:
    name = "stackexchange"
    fallback_to_generic = False

    # True for Stack Exchange question URLs.
    def matches(self, url: str) -> bool:
        return is_stackexchange_question_url(url)

    # Fetch and format the question as markdown.
    async def read(self, url: str, ctx: FetchContext) -> PageResult:
        markdown = await fetch_stackexchange_question(url, timeout=ctx.timeout)
        ok = bool(markdown) and not markdown.lstrip().lower().startswith("error:")
        return PageResult(
            markdown=markdown or f"Error: Stack Exchange fetch failed for {url}",
            ok=ok,
            method="stackexchange_api",
            error="" if ok else (markdown or "stackexchange fetch failed"),
        )


HANDLER = StackExchangeHandler()
