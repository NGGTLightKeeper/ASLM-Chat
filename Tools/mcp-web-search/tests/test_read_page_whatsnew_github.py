# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

# Integration tests for read_page compression on cpython whatsnew 3.13.rst.
# Uses the canonical GitHub blob URL as fixture content (live fetch, module-scoped).
# Run fast path (BM25 + service, network only):
#   pytest tests/test_read_page_whatsnew_github.py -m "integration and not gliner" -q
# Include GLiNER (GPU + model download, slow):
#   pytest tests/test_read_page_whatsnew_github.py -q

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

WHATSNEW_URL = "https://github.com/python/cpython/blob/main/Doc/whatsnew/3.13.rst"
WHATSNEW_FOCUS = "free-threaded GIL"
COMPRESS_THRESHOLD = 10_000
COMPRESS_TARGET = 10_000
MAX_PAGE_CHARS = 20_000

pytestmark = pytest.mark.integration


# whatsnew_rst_markdown — module-scoped live fetch of cpython 3.13 whatsnew RST as markdown.

@pytest.fixture(scope="module")
def whatsnew_rst_markdown() -> str:
    # _fetch — async github page fetch for fixture setup.
    async def _fetch() -> str:
        from custom_domains.github import fetch_github_page

        return await fetch_github_page(WHATSNEW_URL, timeout=30.0)

    try:
        markdown = asyncio.run(_fetch())
    except Exception as exc:
        pytest.skip(f"github fetch failed: {exc}")

    if markdown.lstrip().lower().startswith("error:"):
        pytest.skip(f"github fetch error: {markdown[:300]}")
    if len(markdown) < COMPRESS_THRESHOLD:
        pytest.skip(f"expected >={COMPRESS_THRESHOLD} chars, got {len(markdown)}")
    if "What's New" not in markdown and "whatsnew" not in markdown.lower():
        pytest.skip("unexpected page content (not cpython 3.13 whatsnew)")
    return markdown


# _compress — run compress_read_page_markdown with BM25 and optional GLiNER.

def _compress(
    markdown: str,
    *,
    focus: str = WHATSNEW_FOCUS,
    enable_gliner: bool,
) -> str:
    from core.extract.content_processor import compress_read_page_markdown

    return compress_read_page_markdown(
        markdown,
        url=WHATSNEW_URL,
        focus=focus,
        max_chars=MAX_PAGE_CHARS,
        compress_threshold=COMPRESS_THRESHOLD,
        compress_target=COMPRESS_TARGET,
        enable_compress=True,
        enable_gliner=enable_gliner,
    )


# _gliner_runtime_ready — skip GLiNER tests when package or full_gpu unavailable.

def _gliner_runtime_ready() -> tuple[bool, str]:
    from core.config.hardware import get_hardware_profile
    from core.extract.gliner_wrapper import is_gliner_available

    if not is_gliner_available():
        return False, "gliner package/model not available"
    if get_hardware_profile() != "full_gpu":
        return False, f"GLiNER requires full_gpu, got {get_hardware_profile()!r}"
    return True, ""


# Live fetch and BM25 compression — document length and focus terms preserved.

# test_github_whatsnew_fetch_is_long_document — fixture markdown exceeds threshold and mentions GIL.

def test_github_whatsnew_fetch_is_long_document(whatsnew_rst_markdown: str) -> None:
    assert len(whatsnew_rst_markdown) > COMPRESS_THRESHOLD * 5
    assert "free-threaded" in whatsnew_rst_markdown
    assert "GIL" in whatsnew_rst_markdown


# test_github_whatsnew_bm25_compress_keeps_focus — BM25 compress stays under budget with focus terms.

def test_github_whatsnew_bm25_compress_keeps_focus(whatsnew_rst_markdown: str) -> None:
    out = _compress(whatsnew_rst_markdown, enable_gliner=False)

    assert len(out) <= COMPRESS_TARGET + 500
    assert len(out) < len(whatsnew_rst_markdown)
    assert "free-threaded" in out
    assert "GIL" in out


# GLiNER compression — GPU path when runtime ready.

# test_github_whatsnew_gliner_compress_keeps_focus — GLiNER compress under budget with focus terms.

@pytest.mark.gliner
def test_github_whatsnew_gliner_compress_keeps_focus(whatsnew_rst_markdown: str) -> None:
    ready, reason = _gliner_runtime_ready()
    if not ready:
        pytest.skip(reason)

    out = _compress(whatsnew_rst_markdown, enable_gliner=True)

    assert len(out) <= COMPRESS_TARGET + 500
    assert len(out) < len(whatsnew_rst_markdown)
    assert "free-threaded" in out


# test_github_whatsnew_gliner_and_bm25_both_under_budget — both compressors meet size and focus checks.

@pytest.mark.gliner
def test_github_whatsnew_gliner_and_bm25_both_under_budget(whatsnew_rst_markdown: str) -> None:
    ready, reason = _gliner_runtime_ready()
    if not ready:
        pytest.skip(reason)

    bm25_out = _compress(whatsnew_rst_markdown, enable_gliner=False)
    gliner_out = _compress(whatsnew_rst_markdown, enable_gliner=True)

    for label, text in (("bm25", bm25_out), ("gliner", gliner_out)):
        assert len(text) <= COMPRESS_TARGET + 500, label
        assert "free-threaded" in text, label


# ReadPageService integration — mocked github fetch, BM25 and GLiNER service paths.

# test_read_page_service_whatsnew_bm25_path — service.read compresses fixture via BM25 without live fetch.

def test_read_page_service_whatsnew_bm25_path(
    whatsnew_rst_markdown: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # fake_github — return module fixture instead of network.
    async def fake_github(url: str, timeout: float = 20.0) -> str:
        assert url == WHATSNEW_URL
        return whatsnew_rst_markdown

    # _run — invoke ReadPageService.read with patched github fetch.
    async def _run() -> str:
        monkeypatch.setattr("services.read_page._fetch_github_page", fake_github)

        from services.read_page import ReadPageOptions, ReadPageService

        service = ReadPageService(
            options=ReadPageOptions(focus=WHATSNEW_FOCUS, max_chars=MAX_PAGE_CHARS),
        )
        return await service.read(WHATSNEW_URL)

    result = asyncio.run(_run())

    assert not result.lstrip().lower().startswith("error:")
    assert len(result) <= COMPRESS_TARGET + 500
    assert len(result) < len(whatsnew_rst_markdown)
    assert "free-threaded" in result
    assert "GIL" in result


# test_read_page_service_whatsnew_gliner_path — service.read with enable_gliner config and mocked fetch.

@pytest.mark.gliner
def test_read_page_service_whatsnew_gliner_path(
    whatsnew_rst_markdown: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready, reason = _gliner_runtime_ready()
    if not ready:
        pytest.skip(reason)

    # fake_github — return module fixture instead of network.
    async def fake_github(url: str, timeout: float = 20.0) -> str:
        return whatsnew_rst_markdown

    from core.config import load_search_config

    cfg = load_search_config()
    cfg_gliner = replace(cfg, search=replace(cfg.search, enable_gliner=True))

    # _run — invoke ReadPageService.read with GLiNER config and patched github fetch.
    async def _run() -> str:
        monkeypatch.setattr("services.read_page.load_search_config", lambda: cfg_gliner)
        monkeypatch.setattr("services.read_page._fetch_github_page", fake_github)

        from services.read_page import ReadPageOptions, ReadPageService

        service = ReadPageService(
            options=ReadPageOptions(focus=WHATSNEW_FOCUS, max_chars=MAX_PAGE_CHARS),
        )
        return await service.read(WHATSNEW_URL)

    result = asyncio.run(_run())

    assert not result.lstrip().lower().startswith("error:")
    assert len(result) <= COMPRESS_TARGET + 500
    assert "free-threaded" in result
