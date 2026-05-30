import json
import os
from urllib.parse import urlparse

import pytest

from core.extract.content_processor import PreviewPayload
from core.models.search import SearchResult
from core.query import infer_query_types_hybrid
from core.query.aslm_embedding_runtime import (
    default_query_classifier_path,
    default_source_relevance_path,
    format_source_relevance_input,
    load_aslm_embedding_export,
)
from core.registry.domain_registry import get_registry
from core.registry.trust_registry import get_trust_registry
from services.web_search import (
    _parse_query_profile,
    _result_score,
    _triage_one_result,
)


pytestmark = pytest.mark.integration


EVAL_CASES = [
    {
        "query": "c++ vector erase complexity",
        "results": [
            {
                "url": "https://en.cppreference.com/w/cpp/container/vector/erase",
                "title": "std::vector::erase - cppreference.com",
                "snippet": "C++ reference for vector erase complexity, iterator invalidation, and examples.",
                "preview": "The erase member function removes elements from a vector. Complexity is linear in the number of elements after erased elements.",
            },
            {
                "url": "https://stackoverflow.com/questions/347441/how-can-you-erase-elements-from-a-vector-while-iterating",
                "title": "Erase elements from a vector while iterating",
                "snippet": "Stack Overflow discussion about C++ vector erase and iterator invalidation.",
                "preview": "Use the erase-remove idiom or assign the iterator returned by erase when removing elements during iteration.",
            },
            {
                "url": "https://www.reddit.com/r/cpp/comments/vector_erase/",
                "title": "Why is vector erase slow?",
                "snippet": "Forum discussion with mixed advice about vector erase performance.",
                "preview": "Users discuss contiguous storage, shifting elements, and alternatives such as deque or list.",
            },
        ],
    },
    {
        "query": "reactive oxygen species pubmed",
        "results": [
            {
                "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
                "title": "Reactive oxygen species in cellular signaling",
                "snippet": "PubMed indexed abstract about reactive oxygen species and oxidative stress.",
                "preview": "Reactive oxygen species participate in redox signaling and oxidative damage. This review summarizes mechanisms and clinical implications.",
            },
            {
                "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123456/",
                "title": "Reactive oxygen species and inflammation",
                "snippet": "Full text article from PubMed Central about ROS and inflammation.",
                "preview": "The article reviews ROS generation, antioxidant systems, and inflammatory pathways.",
            },
            {
                "url": "https://react.dev/reference/react",
                "title": "React Reference Overview",
                "snippet": "React documentation for components and hooks.",
                "preview": "React is a JavaScript library for building user interfaces with components.",
            },
        ],
    },
    {
        "query": "best laptop under 1000",
        "results": [
            {
                "url": "https://geizhals.at/?cat=nb",
                "title": "Laptop price comparison",
                "snippet": "Compare laptop prices and specifications under 1000.",
                "preview": "Filter notebooks by CPU, RAM, display, storage, and price from multiple retailers.",
            },
            {
                "url": "https://www.bestbuy.com/site/searchpage.jsp?st=laptop+under+1000",
                "title": "Laptops under $1000",
                "snippet": "Retail catalog of laptops under $1000.",
                "preview": "Shop laptops by brand, processor, screen size, and sale pricing.",
            },
            {
                "url": "https://www.reddit.com/r/SuggestALaptop/comments/best_under_1000/",
                "title": "Best laptop under 1000?",
                "snippet": "Forum recommendations for laptops under 1000.",
                "preview": "Users compare battery life, keyboard quality, repairability, and discounts.",
            },
        ],
    },
    {
        "query": "cat behavior",
        "results": [
            {
                "url": "https://www.aspca.org/pet-care/cat-care/cat-behavior",
                "title": "Cat Behavior",
                "snippet": "Guide to common cat behavior and care.",
                "preview": "Cats communicate through body language, vocalization, scratching, play, and changes in routine.",
            },
            {
                "url": "https://en.wikipedia.org/wiki/Cat_behavior",
                "title": "Cat behavior - Wikipedia",
                "snippet": "Overview of domestic cat behavior.",
                "preview": "Cat behavior includes social interaction, hunting, grooming, territorial marking, and communication.",
            },
            {
                "url": "https://en.cppreference.com/w/cpp/language/behavior",
                "title": "Undefined behavior - cppreference.com",
                "snippet": "C++ language reference for undefined behavior.",
                "preview": "Undefined behavior in C++ allows the implementation to assume unreachable program states.",
            },
        ],
    },
]


def _class_mix(hybrid: list[tuple[str, float, str]]) -> dict[str, float]:
    return {name: float(weight) for name, weight, _reason in hybrid}


def _trust_entry_for_url(trust_registry, url: str):
    host = urlparse(url).netloc.lower()
    for pattern, entry in getattr(trust_registry, "_lookup", {}).items():
        if host == pattern or host.endswith("." + pattern):
            return entry
    return None


def _domain_multiplier(url: str, class_mix: dict[str, float]) -> dict[str, float | str]:
    info = get_registry().lookup(url)
    base = float(info.base_weight or 1.0)
    class_weight = sum(
        weight * float(info.class_weights.get(name, 1.0))
        for name, weight in class_mix.items()
    ) or 1.0
    demotion = sum(
        weight * float(info.hard_demotions.get(name, 1.0))
        for name, weight in class_mix.items()
    ) or 1.0

    path = urlparse(url).path or "/"
    path_weight = 1.0
    matched_path = ""
    for candidate in sorted(info.path_weights, key=lambda item: len(item.path_prefix), reverse=True):
        if path.startswith(candidate.path_prefix):
            matched_path = candidate.path_prefix
            path_weight = (
                sum(
                    weight * float(candidate.class_weights.get(name, 1.0))
                    for name, weight in class_mix.items()
                )
                or 1.0
            )
            break

    raw = base * class_weight * demotion * path_weight
    return {
        "pattern": info.pattern,
        "method": info.method,
        "tier": info.tier,
        "base": round(base, 4),
        "class_weight": round(class_weight, 4),
        "demotion": round(demotion, 4),
        "path_weight": round(path_weight, 4),
        "matched_path": matched_path,
        "raw": round(raw, 4),
        "bounded": round(max(0.55, min(1.45, raw)), 4),
    }


def _trust_multiplier(trust_registry, url: str, class_mix: dict[str, float]) -> dict[str, float | str]:
    entry = _trust_entry_for_url(trust_registry, url)
    if entry is None:
        return {"tier": "?", "affinity": 1.0, "pattern": ""}
    affinity = (
        sum(
            weight * float(entry.class_affinity.get(name, 1.0))
            for name, weight in class_mix.items()
        )
        or 1.0
    )
    return {
        "tier": entry.tier,
        "affinity": round(max(0.55, min(1.25, affinity)), 4),
        "pattern": entry.pattern,
    }


def test_neural_web_search_domain_eval_trace() -> None:
    if os.environ.get("RUN_NEURAL_WEB_SEARCH_EVAL") != "1":
        pytest.skip("set RUN_NEURAL_WEB_SEARCH_EVAL=1 to run local ASLM embedding web-search eval")

    query_model = load_aslm_embedding_export(str(default_query_classifier_path()))
    source_model = load_aslm_embedding_export(str(default_source_relevance_path()))
    trust_registry = get_trust_registry()

    traces = []
    for case in EVAL_CASES:
        query = case["query"]
        query_prediction = query_model.predict([query])[0]
        hybrid = infer_query_types_hybrid(query, query_prediction.labels)
        mix = _class_mix(hybrid)
        primary = hybrid[0][0] if hybrid else "general"
        profile = _parse_query_profile(query)

        rows = []
        source_inputs = [
            format_source_relevance_input(
                query=query,
                title=item["title"],
                url=item["url"],
                snippet=item["snippet"],
                preview=item["preview"],
            )
            for item in case["results"]
        ]
        source_predictions = source_model.predict(source_inputs)

        for idx, (item, source_prediction) in enumerate(zip(case["results"], source_predictions, strict=True)):
            result = SearchResult(
                url=item["url"],
                title=item["title"],
                snippet=item["snippet"],
                engine="eval:fixture",
            )
            triage = _triage_one_result(
                result,
                query,
                index=idx,
                total=len(case["results"]),
                trust_reg=trust_registry,
                rep_store=None,
            )
            payload = PreviewPayload(
                text=item["preview"],
                semantic_score=source_prediction.score,
                quality_score=0.75,
                clean_chars=len(item["preview"]),
                strategy_used="eval_fixture",
            )
            current_score = _result_score(
                result,
                payload,
                index=idx,
                total=len(case["results"]),
                query=query,
                profile=profile,
                query_type=primary,
                rep_store=None,
            )
            domain = _domain_multiplier(result.url, mix)
            trust = _trust_multiplier(trust_registry, result.url, mix)
            proposed_multiplier = float(domain["bounded"]) * float(trust["affinity"])
            rows.append(
                {
                    "url": result.url,
                    "title": result.title,
                    "trust_tier": result.trust_tier,
                    "triage": {
                        "skip": triage.skip,
                        "policy": triage.fetch_policy,
                        "score": round(triage.score, 4),
                    },
                    "source_model": {
                        "score": round(source_prediction.score, 4),
                        "top_labels": [
                            [name, round(score, 4)]
                            for name, score in source_prediction.top(3)
                        ],
                    },
                    "domain": domain,
                    "trust": trust,
                    "current_final_score": round(current_score, 4),
                    "domain_adjusted_score": round(current_score * proposed_multiplier, 4),
                }
            )

        traces.append(
            {
                "query": query,
                "query_model": {
                    "score": round(query_prediction.score, 4),
                    "top_labels": [
                        [name, round(score, 4)]
                        for name, score in query_prediction.top(5)
                    ],
                },
                "hybrid": [
                    [name, weight, reason]
                    for name, weight, reason in hybrid
                ],
                "results": sorted(rows, key=lambda row: row["domain_adjusted_score"], reverse=True),
            }
        )

    assert traces
    rendered = json.dumps(traces, indent=2, ensure_ascii=False)
    assert "domain_adjusted_score" in rendered
    print(rendered)
