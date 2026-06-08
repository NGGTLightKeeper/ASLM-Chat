"""DDGS class implementation."""

import logging
import os
import time
from math import ceil
from types import TracebackType
from typing import Any, ClassVar

from .base import BaseSearchEngine
from .engines import ENGINES
from .exceptions import DDGSException, TimeoutException
from .routing import LANGUAGE_REGION, ROUTING_STATE, infer_language
from .utils import _expand_proxy_tb_alias

logger = logging.getLogger(__name__)


class DDGS:
    """DDGS | Dux Distributed Global Search.

    A metasearch library that aggregates results from diverse web search services.

    Args:
        proxy: The proxy to use for the search. Defaults to None.
        timeout: The timeout for the search. Defaults to 5.
        verify: bool (True to verify, False to skip) or str path to a PEM file. Defaults to True.

    Attributes:
        threads: The maximum number of threads per search. Defaults to None (automatic, based on max_results).

    Raises:
        DDGSException: If an error occurs during the search.

    Example:
        >>> from core.ddgs import DDGS
        >>> results = DDGS().text("python")

    """

    threads: ClassVar[int | None] = None

    def __init__(
        self,
        proxy: str | None = None,
        timeout: int | None = 5,
        *,
        verify: bool | str = True,
    ) -> None:
        self._proxy = _expand_proxy_tb_alias(proxy) or os.environ.get("DDGS_PROXY")
        self._timeout = timeout
        self._verify = verify
        self._engines_cache: dict[tuple[type[BaseSearchEngine[Any]], int], BaseSearchEngine[Any]] = {}

    def __enter__(self) -> "DDGS":  # noqa: PYI034
        """Enter the context manager and return the DDGS instance."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        """Exit the context manager."""

    def _get_engines(
        self,
        category: str,
        backend: str,
    ) -> list[BaseSearchEngine[Any]]:
        """Retrieve a list of search engine instances for a given category and backend.

        Args:
            category: The search-engine category.
            backend: A single or comma-delimited backends. Defaults to "auto".

        Returns:
            A list of initialized search engine instances corresponding to the specified
            category and backend. Instances are cached for reuse.

        """
        if isinstance(backend, list):  # deprecated
            backend = ",".join(backend)
        backend_list = [x.strip() for x in backend.split(",") if x.strip()]
        keys = list(ENGINES[category]) if any(x in {"auto", "all"} for x in backend_list) else backend_list

        engine_classes = []
        invalid_keys = []
        for key in keys:
            if engine_class := ENGINES[category].get(key):
                engine_classes.append(engine_class)
            else:
                invalid_keys.append(key)

        if invalid_keys:
            logger.warning(
                "%s - backends do not exist or are disabled. Available: %s",
                ", ".join(sorted(invalid_keys)),
                ", ".join(sorted(engine_keys)),
            )

        # Initialize and cache engine instances
        instances = []
        for engine_class in engine_classes:
            # If already cached, use the cached instance
            cache_key = (engine_class, int(self._timeout or 0))
            if cache_key in self._engines_cache:
                instances.append(self._engines_cache[cache_key])
            # If not cached, create a new instance
            else:
                engine_instance = engine_class(proxy=self._proxy, timeout=self._timeout, verify=self._verify)
                self._engines_cache[cache_key] = engine_instance
                instances.append(engine_instance)

        if not instances:
            logger.warning("backend is not set. Using 'auto'")
            return self._get_engines(category, "auto")

        return instances

    def _engine(self, name: str, timeout: float) -> BaseSearchEngine[Any]:
        engine_class = ENGINES["text"][name]
        cache_key = (engine_class, max(1, int(timeout)))
        if cache_key not in self._engines_cache:
            self._engines_cache[cache_key] = engine_class(
                proxy=self._proxy,
                timeout=cache_key[1],
                verify=self._verify,
            )
        return self._engines_cache[cache_key]

    def _search_sync(  # noqa: C901
        self,
        category: str,
        query: str,
        keywords: str | None = None,
        *,
        region: str = "us-en",
        safesearch: str = "moderate",
        timelimit: str | None = None,
        max_results: int | None = 10,
        page: int = 1,
        backend: str = "auto",
        language: str | None = None,
        query_types: list[str] | None = None,
        max_attempts: int = 2,
        **kwargs: str,
    ) -> list[dict[str, Any]]:
        """Perform a search across engines in the given category.

        Args:
            category: The search-engine category.
            query: The search query.
            keywords: Deprecated alias for `query`.
            region: The region to use for the search (e.g., us-en, uk-en, ru-ru, etc.).
            safesearch: The safesearch setting (e.g., on, moderate, off).
            timelimit: The timelimit for the search (e.g., d, w, m, y) or custom date range.
            max_results: The maximum number of results to return. Defaults to 10.
            page: The page of results to return. Defaults to 1.
            backend: A single or comma-delimited backends. Defaults to "auto".
            **kwargs: Additional keyword arguments to pass to the search engines.

        Returns:
            A list of dictionaries containing the search results.

        """
        query = keywords or query
        if not query:
            msg = "query is mandatory."
            raise DDGSException(msg)

        requested = [item.strip() for item in backend.split(",") if item.strip()]
        auto = any(item in {"auto", "all"} for item in requested)
        detected_language = infer_language(query)
        language = detected_language if detected_language != "en" else (language or "en")
        region = LANGUAGE_REGION.get(language, region)
        if auto:
            plan = ROUTING_STATE.plan(
                set(ENGINES[category]),
                language=language,
                query_types=set(query_types or ("general",)),
                max_attempts=max(1, max_attempts),
            )
        else:
            plan = [name for name in requested if name in ENGINES[category]]

        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        err: BaseException | None = None
        hard_deadline = time.perf_counter() + max(1.0, float(self._timeout or 5))
        per_engine_limit = max_results
        if auto and max_results:
            per_engine_limit = max(1, ceil(max_results / max(1, len(plan))))
        for index, name in enumerate(plan):
            remaining = hard_deadline - time.perf_counter()
            if remaining <= 0:
                break
            attempts_left = max(1, len(plan) - index)
            fair_share = max(1.0, remaining / attempts_left)
            attempt_timeout = min(remaining, fair_share, ROUTING_STATE.attempt_timeout(name, remaining))
            started = time.perf_counter()
            try:
                engine_results = self._engine(name, attempt_timeout).search(
                    query,
                    region=region,
                    safesearch=safesearch,
                    timelimit=timelimit,
                    page=page,
                    **kwargs,
                ) or []
                latency = time.perf_counter() - started
                ROUTING_STATE.record(name, latency, bool(engine_results))
                added = 0
                for result in engine_results:
                    item = dict(result.__dict__)
                    url = str(item.get("href") or "").strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    item["_engine"] = name
                    results.append(item)
                    added += 1
                    if per_engine_limit and added >= per_engine_limit:
                        break
                    if max_results and len(results) >= max_results:
                        break
                if not auto and results:
                    break
            except Exception as ex:  # noqa: BLE001
                err = ex
                ROUTING_STATE.record(name, time.perf_counter() - started, False, ex)
                logger.info("Error in engine %s: %r", name, ex)
            if max_results and len(results) >= max_results:
                break

        if results:
            return results[:max_results] if max_results else results

        if "timed out" in f"{err}":
            raise TimeoutException(err)
        raise DDGSException(err or "No results found.")

    def text(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:  # noqa: ANN401
        """Perform a text search."""
        return self._search_sync("text", query, **kwargs)
