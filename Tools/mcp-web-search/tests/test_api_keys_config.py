# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import json

from core.config import api_keys


# Load all hosted provider keys from the generated JSON document.
def test_load_api_keys_reads_generated_json(tmp_path) -> None:
    path = tmp_path / "api_keys.json"
    path.write_text(
        json.dumps(
            {
                "search": {
                    "hosted_api": {
                        "tavily_api_key": "tavily",
                        "firecrawl_api_key": "firecrawl",
                        "brave_api_key": "brave",
                        "serpapi_api_key": "serpapi",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    loaded = api_keys.load_api_keys(path)

    assert loaded.search.hosted_api.tavily_api_key == "tavily"
    assert loaded.search.hosted_api.firecrawl_api_key == "firecrawl"
    assert loaded.search.hosted_api.brave_api_key == "brave"
    assert loaded.search.hosted_api.serpapi_api_key == "serpapi"


# Return an empty key set without creating a replacement file when JSON is absent.
def test_load_api_keys_does_not_bootstrap_missing_file(tmp_path) -> None:
    path = tmp_path / "api_keys.json"

    loaded = api_keys.load_api_keys(path)

    assert loaded.search.hosted_api.tavily_api_key is None
    assert not path.exists()


# Treat blank provider values as disabled hosted integrations.
def test_load_api_keys_normalizes_blank_values(tmp_path) -> None:
    path = tmp_path / "api_keys.json"
    path.write_text(
        json.dumps({"search": {"hosted_api": {"tavily_api_key": "   "}}}),
        encoding="utf-8",
    )

    loaded = api_keys.load_api_keys(path)

    assert loaded.search.hosted_api.tavily_api_key is None
