from core.query.benchmark_queries import BENCHMARK_QUERIES


def test_benchmark_queries_are_complex_multilingual_and_unique() -> None:
    ids = [item["id"] for item in BENCHMARK_QUERIES]
    languages = {item["language"] for item in BENCHMARK_QUERIES}

    assert len(ids) == len(set(ids))
    assert len(BENCHMARK_QUERIES) >= 6
    assert len(languages) >= 5
    assert all(len(item["query"].split()) >= 5 for item in BENCHMARK_QUERIES)
