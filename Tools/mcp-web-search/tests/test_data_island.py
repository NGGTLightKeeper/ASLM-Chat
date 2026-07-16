# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""JSON data-island fallback — ported regression tests from webclaw's data_island.rs.

The cases mirror the reference suite (Contentful rich text, quotes, content-vs-identifier
heuristic, DOM dedup, chunk dedup) plus the sparse-gate wiring specific to our read path.
"""

from __future__ import annotations

from core.extract.data_island import _is_content_text, try_extract_data_islands


def test_extracts_contentful_rich_text():
    html = """<html><body>
    <script type="application/json" data-target="react-app.embeddedData">
    {"payload":{"contentfulRawJsonResponse":{"includes":{"Entry":[
        {"fields":{
            "heading":"Ship faster with secure CI/CD",
            "subheading":{"content":[{"content":[{"value":"Automate builds, tests, and deployments."}]}]}
        }},
        {"fields":{
            "heading":"Built-in application security",
            "description":{"content":[{"content":[{"value":"Use AI to find and fix vulnerabilities so your team can ship more secure software faster."}]}]}
        }}
    ]}}}}
    </script>
    </body></html>"""
    result = try_extract_data_islands(html, 0, "")
    assert result is not None
    assert "Ship faster with secure CI/CD" in result
    assert "Automate builds, tests, and deployments" in result
    assert "Built-in application security" in result
    assert "find and fix vulnerabilities" in result


def test_skips_when_dom_has_enough_content():
    html = """<html><body>
    <script type="application/json">{"heading":"Foo","description":"Some long description here."}</script>
    </body></html>"""
    # dom_word_count above the sparse threshold → never inspect islands.
    assert try_extract_data_islands(html, 500, "") is None


def test_skips_non_content_strings():
    assert not _is_content_text("abc123")
    assert not _is_content_text("https://example.com/foo/bar")
    assert not _is_content_text("/home Customer Stories: Logo")
    assert not _is_content_text("a1b2c3d4e5f6a1b2c3d4e5f6")
    assert _is_content_text("Automate builds, tests, and deployments with CI/CD.")


def test_extracts_quotes():
    html = """<html><body>
    <script type="application/json">
    {"fields":{"quote":{"content":[{"content":[{"value":"GitHub frees us from maintaining our own infrastructure."}]}]},"position":"CTO at Example Corp"}}
    </script>
    </body></html>"""
    result = try_extract_data_islands(html, 0, "")
    assert result is not None
    assert "> GitHub frees us from maintaining our own infrastructure." in result
    assert "CTO at Example Corp" in result


def test_skips_content_already_in_dom():
    html = """<html><body>
    <script type="application/json">
    {"fields":{"heading":"Already in DOM heading","description":"This text already appears in the DOM markdown output."}}
    </script>
    </body></html>"""
    existing = "# Already in DOM heading\n\nThis text already appears in the DOM markdown output."
    assert try_extract_data_islands(html, 10, existing) is None


def test_deduplicates_chunks():
    html = """<html><body>
    <script type="application/json">
    {"a":{"heading":"Same heading here","description":"Same body content across multiple entries."},
     "b":{"heading":"Same heading here","description":"Same body content across multiple entries."}}
    </script>
    </body></html>"""
    result = try_extract_data_islands(html, 0, "")
    assert result is not None
    assert result.count("Same body content across multiple entries") == 1


def test_stat_string_array():
    html = """<html><body>
    <script type="application/json">
    {"stats":["100M+ developers building", "#1 rated developer platform worldwide"]}
    </script>
    </body></html>"""
    result = try_extract_data_islands(html, 0, "")
    assert result is not None
    assert "100M+ developers building" in result
    assert "#1 rated developer platform worldwide" in result


def test_media_keys_not_extracted_as_prose():
    # alt / image / logo fields must not surface as content, even though they are strings.
    html = """<html><body>
    <script type="application/json">
    {"alt":"A person typing on a laptop keyboard closeup", "logoImage":"Company logo dark variant"}
    </script>
    </body></html>"""
    assert try_extract_data_islands(html, 0, "") is None


def test_no_script_returns_none():
    assert try_extract_data_islands("<html><body><p>hi</p></body></html>", 0, "") is None


def test_malformed_json_ignored():
    html = """<html><body>
    <script type="application/json">{not valid json at all,,,}</script>
    </body></html>"""
    assert try_extract_data_islands(html, 0, "") is None


def test_tiny_json_skipped():
    # Below the 50-char floor → not worth parsing.
    html = '<html><body><script type="application/json">{"a":"b"}</script></body></html>'
    assert try_extract_data_islands(html, 0, "") is None
