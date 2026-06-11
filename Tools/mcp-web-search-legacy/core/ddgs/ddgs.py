"""DDGS class implementation."""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import ceil
from types import TracebackType
from typing import Any, ClassVar

from .base import BaseSearchEngine
from .engines import ENGINES
from .exceptions import DDGSException, TimeoutException
from .routing import (
    LANGUAGE_REGION,
    ROUTING_STATE,
    a_tier_engine_count,
    a_tier_result_cap,
    b_tier_result_cap,
    infer_language,
)
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
        class_weights: dict[str, float] | None = None,
        max_attempts: int = 2,
        routing_profile: str = "stability",
        routing_strategy: str = "legacy",
        effort: str = "medium",
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

        if routing_strategy == "tiered_ab" and any(
            item in {"auto", "all"} for item in backend.split(",")
        ):
            return self._search_sync_tiered_ab(
                category=category,
                query=query,
                region=region,
                safesearch=safesearch,
                timelimit=timelimit,
                max_results=max_results,
                page=page,
                language=language,
                query_types=query_types,
                class_weights=class_weights,
                max_attempts=max_attempts,
                effort=effort,
                **kwargs,
            )

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
                class_weights=class_weights,
                max_attempts=max(1, max_attempts + 2),
                routing_profile=routing_profile,
            )
        else:
            plan = [name for name in requested if name in ENGINES[category]]

        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        result_by_url: dict[str, dict[str, Any]] = {}
        err: BaseException | None = None
        hard_deadline = time.perf_counter() + max(1.0, float(self._timeout or 5))
        per_engine_limit = max_results
        if auto and max_results:
            per_engine_limit = max(1, ceil(max_results / max(1, max_attempts)))
        attempted: set[str] = set()
        successful_attempts = 0
        total_attempt_limit = max_attempts + 2 if auto else len(plan)

        def run_engine(name: str, attempt_timeout: float) -> tuple[str, list[Any], BaseException | None, float]:
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
                return name, engine_results, None, time.perf_counter() - started
            except Exception as ex:  # noqa: BLE001
                return name, [], ex, time.perf_counter() - started

        while plan and len(attempted) < total_attempt_limit:
            remaining = hard_deadline - time.perf_counter()
            if remaining <= 0:
                break
            wave_size = 1
            if auto and routing_profile == "quality":
                wave_size = ROUTING_STATE.quality_concurrency(set(ENGINES[category]))
                if wave_size == 1:
                    logger.info("quality search throttled to sequential execution after timeout pressure")
            wave: list[str] = []
            while plan and len(wave) < wave_size and len(attempted) + len(wave) < total_attempt_limit:
                name = plan.pop(0)
                if name not in attempted and name not in wave:
                    wave.append(name)
            if not wave:
                break

            attempts_left = max(1, total_attempt_limit - len(attempted))
            waves_left = max(1, ceil(attempts_left / len(wave)))
            fair_share = max(1.0, remaining / waves_left)
            jobs = [
                (name, min(remaining, fair_share, ROUTING_STATE.attempt_timeout(name, remaining)))
                for name in wave
            ]
            attempted.update(wave)
            if len(jobs) == 1:
                outcomes = [run_engine(*jobs[0])]
            else:
                with ThreadPoolExecutor(max_workers=2, thread_name_prefix="ddgs-quality") as executor:
                    futures = [executor.submit(run_engine, *job) for job in jobs]
                    outcomes = [future.result() for future in as_completed(futures)]

            needs_replan = False
            for name, engine_results, engine_error, latency in outcomes:
                if engine_error is not None:
                    err = engine_error
                    ROUTING_STATE.record(name, latency, False, engine_error)
                    logger.info(
                        "engine.attempt engine=%s latency=%.3fs results=0 success=false error=%r",
                        name,
                        latency,
                        engine_error,
                    )
                    needs_replan = True
                    continue

                ROUTING_STATE.record(name, latency, bool(engine_results))
                logger.info(
                    "engine.attempt engine=%s latency=%.3fs results=%d success=%s",
                    name,
                    latency,
                    len(engine_results),
                    str(bool(engine_results)).lower(),
                )
                needs_replan = needs_replan or not engine_results
                added = 0
                for result in engine_results:
                    item = dict(result.__dict__)
                    url = str(item.get("href") or "").strip()
                    if not url:
                        continue
                    if url in seen_urls:
                        existing = result_by_url[url]
                        existing["_votes"] = int(existing.get("_votes", 1)) + 1
                        engines = list(existing.get("_engines") or [existing.get("_engine")])
                        if name not in engines:
                            engines.append(name)
                        existing["_engines"] = engines
                        continue
                    seen_urls.add(url)
                    item["_engine"] = name
                    item["_engines"] = [name]
                    item["_votes"] = 1
                    results.append(item)
                    result_by_url[url] = item
                    added += 1
                    if per_engine_limit and added >= per_engine_limit:
                        break
                    if max_results and len(results) >= max_results:
                        break
                if added:
                    successful_attempts += 1
                if not auto and results:
                    break
            if needs_replan and auto:
                fallback = ROUTING_STATE.plan(
                    set(ENGINES[category]) - attempted,
                    language=language,
                    query_types=set(query_types or ("general",)),
                    class_weights=class_weights,
                    max_attempts=max(1, total_attempt_limit - len(attempted)),
                    prefer_tier="B" if routing_profile == "stability" else None,
                    routing_profile=routing_profile,
                )
                plan = fallback + [candidate for candidate in plan if candidate not in fallback]
            if max_results and len(results) >= max_results:
                break
            if auto and successful_attempts >= max_attempts:
                break

        if results:
            if routing_profile == "quality":
                results.sort(key=lambda item: int(item.get("_votes", 1)), reverse=True)
            logger.info(
                "search profile=%s attempted=%s successful=%d results=%d",
                routing_profile,
                sorted(attempted),
                successful_attempts,
                len(results),
            )
            return results[:max_results] if max_results else results

        if "timed out" in f"{err}":
            raise TimeoutException(err)
        raise DDGSException(err or "No results found.")

    def _search_sync_tiered_ab(  # noqa: C901
        self,
        *,
        category: str,
        query: str,
        region: str,
        safesearch: str,
        timelimit: str | None,
        max_results: int | None,
        page: int,
        language: str | None,
        query_types: list[str] | None,
        class_weights: dict[str, float] | None,
        max_attempts: int,
        effort: str,
        **kwargs: str,
    ) -> list[dict[str, Any]]:
        """Wave 1: A-tier (count scales with effort). Wave 2: B-tier fills the pool."""
        detected_language = infer_language(query)
        language = detected_language if detected_language != "en" else (language or "en")
        region = LANGUAGE_REGION.get(language, region)
        query_type_set = set(query_types or ("general",))
        available = set(ENGINES[category])
        a_target = a_tier_engine_count(effort)
        a_cap = a_tier_result_cap(max_results or 10, a_target)
        hard_deadline = time.perf_counter() + max(1.0, float(self._timeout or 5))
        attempted: set[str] = set()
        a_successes = 0
        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        result_by_url: dict[str, dict[str, Any]] = {}
        err: BaseException | None = None

        def run_engine(name: str, attempt_timeout: float) -> tuple[str, list[Any], BaseException | None, float]:
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
                return name, engine_results, None, time.perf_counter() - started
            except Exception as ex:  # noqa: BLE001
                return name, [], ex, time.perf_counter() - started

        def absorb(
            name: str,
            engine_results: list[Any],
            *,
            per_engine_limit: int,
        ) -> int:
            added = 0
            for result in engine_results:
                item = dict(result.__dict__)
                url = str(item.get("href") or "").strip()
                if not url:
                    continue
                if url in seen_urls:
                    existing = result_by_url[url]
                    existing["_votes"] = int(existing.get("_votes", 1)) + 1
                    engines = list(existing.get("_engines") or [existing.get("_engine")])
                    if name not in engines:
                        engines.append(name)
                    existing["_engines"] = engines
                    continue
                seen_urls.add(url)
                item["_engine"] = name
                item["_engines"] = [name]
                item["_votes"] = 1
                results.append(item)
                result_by_url[url] = item
                added += 1
                if per_engine_limit and added >= per_engine_limit:
                    break
                if max_results and len(results) >= max_results:
                    break
            return added

        a_reserve = ROUTING_STATE.plan_tier_wave(
            available,
            tier="A",
            count=max(a_target * 2, a_target + 1),
            language=language,
            query_types=query_type_set,
            class_weights=class_weights,
        )
        a_wave: list[str] = []
        while a_reserve and len(a_wave) < a_target:
            name = a_reserve.pop(0)
            if name not in attempted and name not in a_wave:
                a_wave.append(name)

        remaining = hard_deadline - time.perf_counter()
        if remaining > 0 and a_wave:
            jobs = [
                (
                    name,
                    min(remaining, ROUTING_STATE.attempt_timeout(name, remaining)),
                )
                for name in a_wave
            ]
            attempted.update(a_wave)
            if len(jobs) == 1:
                outcomes = [run_engine(*jobs[0])]
            else:
                with ThreadPoolExecutor(max_workers=min(3, len(jobs)), thread_name_prefix="ddgs-tiered-a") as executor:
                    futures = [executor.submit(run_engine, *job) for job in jobs]
                    outcomes = [future.result() for future in as_completed(futures)]

            for name, engine_results, engine_error, latency in outcomes:
                if engine_error is not None:
                    err = engine_error
                    ROUTING_STATE.record(name, latency, False, engine_error)
                    logger.info(
                        "tiered_ab.a engine=%s latency=%.3fs success=false error=%r",
                        name, latency, engine_error,
                    )
                    continue
                ROUTING_STATE.record(name, latency, bool(engine_results))
                added = absorb(name, engine_results, per_engine_limit=a_cap)
                if added:
                    a_successes += 1
                logger.info(
                    "tiered_ab.a engine=%s latency=%.3fs added=%d cap=%d",
                    name, latency, added, a_cap,
                )

            while a_successes < a_target and a_reserve and (hard_deadline - time.perf_counter()) > 0:
                name = a_reserve.pop(0)
                if name in attempted:
                    continue
                attempted.add(name)
                remaining = hard_deadline - time.perf_counter()
                timeout = min(remaining, ROUTING_STATE.attempt_timeout(name, remaining))
                name, engine_results, engine_error, latency = run_engine(name, timeout)
                if engine_error is not None:
                    err = engine_error
                    ROUTING_STATE.record(name, latency, False, engine_error)
                    continue
                ROUTING_STATE.record(name, latency, bool(engine_results))
                added = absorb(name, engine_results, per_engine_limit=a_cap)
                if added:
                    a_successes += 1

        if max_results and len(results) >= max_results:
            logger.info(
                "tiered_ab done phase=A attempted=%s results=%d",
                sorted(attempted), len(results),
            )
            return results[:max_results]

        b_budget = max(1, max_attempts)
        b_reserve = ROUTING_STATE.plan_tier_wave(
            available,
            tier="B",
            count=b_budget + 2,
            language=language,
            query_types=query_type_set,
            class_weights=class_weights,
            exclude=attempted,
        )
        b_successes = 0
        while b_reserve and b_successes < b_budget and (hard_deadline - time.perf_counter()) > 0:
            if max_results and len(results) >= max_results:
                break
            name = b_reserve.pop(0)
            if name in attempted:
                continue
            attempted.add(name)
            remaining_slots = (max_results or 10) - len(results)
            engines_left = max(1, len(b_reserve) + 1)
            b_cap = b_tier_result_cap(remaining_slots, engines_left)
            remaining = hard_deadline - time.perf_counter()
            timeout = min(remaining, ROUTING_STATE.attempt_timeout(name, remaining))
            name, engine_results, engine_error, latency = run_engine(name, timeout)
            if engine_error is not None:
                err = engine_error
                ROUTING_STATE.record(name, latency, False, engine_error)
                logger.info(
                    "tiered_ab.b engine=%s latency=%.3fs success=false error=%r",
                    name, latency, engine_error,
                )
                continue
            ROUTING_STATE.record(name, latency, bool(engine_results))
            added = absorb(name, engine_results, per_engine_limit=b_cap)
            if added:
                b_successes += 1
            logger.info(
                "tiered_ab.b engine=%s latency=%.3fs added=%d cap=%d pool=%d",
                name, latency, added, b_cap, len(results),
            )

        if results:
            logger.info(
                "tiered_ab done attempted=%s a_ok=%d b_ok=%d results=%d",
                sorted(attempted), a_successes, b_successes, len(results),
            )
            return results[:max_results] if max_results else results

        if "timed out" in f"{err}":
            raise TimeoutException(err)
        raise DDGSException(err or "No results found.")

    def text(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:  # noqa: ANN401
        """Perform a text search."""
        return self._search_sync("text", query, **kwargs)
