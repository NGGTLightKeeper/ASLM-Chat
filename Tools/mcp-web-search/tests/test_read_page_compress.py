from __future__ import annotations

from core.extract.content_processor import (
    compress_read_page_markdown,
    derive_read_page_focus,
)


def _long_page(*, filler: str, needle: str, repeats: int = 80) -> str:
    blocks = [filler * 120] * repeats
    blocks.insert(repeats // 2, needle)
    return "\n\n".join(blocks)


def test_derive_read_page_focus_from_url_and_title() -> None:
    url = "https://github.com/python/cpython/blob/main/Doc/whatsnew/3.13.rst"
    md = "# What's New In Python 3.13\n\nbody"
    focus = derive_read_page_focus(url, md)
    assert "whatsnew" in focus.lower()
    assert "3.13" in focus


def test_compress_read_page_uses_bm25_when_gliner_disabled() -> None:
    needle = "UNIQUE_NEEDLE_TOKEN_XYZ compression target paragraph."
    text = _long_page(filler="filler paragraph about nothing. ", needle=needle)
    assert len(text) > 12_000

    out = compress_read_page_markdown(
        text,
        url="https://example.com/docs/guide",
        focus="UNIQUE_NEEDLE_TOKEN_XYZ",
        max_chars=20_000,
        compress_threshold=10_000,
        compress_target=10_000,
        enable_compress=True,
        enable_gliner=False,
    )

    assert len(out) <= 10_500
    assert "UNIQUE_NEEDLE_TOKEN_XYZ" in out


def test_resolve_read_page_compress_query_prefers_explicit_focus() -> None:
    from core.extract.content_processor import _resolve_read_page_compress_query

    url = "https://github.com/python/cpython/blob/main/Doc/whatsnew/3.13.rst"
    md = "# What's New In Python 3.13\n\nbody"
    assert _resolve_read_page_compress_query("free-threaded GIL", url, md) == "free-threaded GIL"


def test_resolve_read_page_compress_query_falls_back_to_derived_focus() -> None:
    from core.extract.content_processor import _resolve_read_page_compress_query

    url = "https://github.com/python/cpython/blob/main/Doc/whatsnew/3.13.rst"
    md = "# What's New In Python 3.13\n\nbody"
    derived = _resolve_read_page_compress_query("", url, md)
    assert "whatsnew" in derived.lower()
    assert "3.13" in derived


def test_compress_read_page_skips_when_below_threshold() -> None:
    text = "short page\n\n" * 5
    out = compress_read_page_markdown(
        text,
        max_chars=20_000,
        compress_threshold=10_000,
        compress_target=10_000,
        enable_compress=True,
        enable_gliner=False,
    )
    assert out == text
