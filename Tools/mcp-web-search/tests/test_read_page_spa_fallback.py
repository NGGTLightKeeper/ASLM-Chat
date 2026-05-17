from __future__ import annotations

import asyncio
from dataclasses import dataclass

from services.read_page import ReadPageService


@dataclass
class _FakeCamoufoxResult:
    url: str
    success: bool = True
    html: str = "<html><body>hydrated app shell with article content</body></html>"
    text: str = ""
    inner_text: str = (
        "Composer 2 vs Auto model pricing\n\n"
        "Auto has flat-rate pricing. Composer 2 Regular is slightly cheaper than Auto. "
        "Auto can route to more capable models while keeping the Auto rate. "
        "Selecting Composer 2 directly is the reliable way to use that model and consume usage more slowly. "
        "This paragraph is intentionally long enough to clear the weak-extraction minimum."
    )
    title: str = ""
    method: str = "camoufox"
    error: str = ""
    duration_sec: float = 0.0


def test_read_page_uses_camoufox_after_weak_network_extraction(monkeypatch) -> None:
    monkeypatch.setattr("services.read_page._cache.get_cached", lambda url: None)

    async def fake_fetch_race(*args, **kwargs) -> str | None:
        return "<html><title>App shell</title><body>Loading...</body></html>"

    async def fake_camoufox(url: str, **kwargs) -> _FakeCamoufoxResult:
        return _FakeCamoufoxResult(url=url)

    monkeypatch.setattr("services.read_page._fetch_race", fake_fetch_race)
    monkeypatch.setattr("services.read_page.is_camoufox_available", lambda: True)
    monkeypatch.setattr("services.read_page.fetch_with_camoufox", fake_camoufox)

    def fake_normalize_page(url: str, raw_html: str) -> str:
        if "hydrated app shell with article content" in raw_html:
            return (
                "# Composer 2 vs Auto model pricing\n\n"
                "Auto has flat-rate pricing.\n\n"
                "Composer 2 Regular is slightly cheaper than Auto.\n\n"
                "Auto can route to more capable models while keeping the Auto rate.\n\n"
                "Selecting Composer 2 directly is the reliable way to use that model and consume usage more slowly.\n\n"
                "This paragraph is intentionally long enough to clear the weak-extraction minimum. "
                "It includes enough surrounding discussion to look like a real hydrated SPA page rather than a title, "
                "a metadata block, or a short loading shell returned before client-side rendering has completed.\n\n"
                "The fallback should prefer this hydrated content because it contains the actual answer text, "
                "multiple substantive paragraphs, and enough context for ranking and citation snippets. "
                "This mirrors forum pages and documentation pages where the first network response only contains "
                "navigation, script tags, and a title while the browser-rendered DOM contains the discussion body."
            )
        return "# App shell\n\nLoading"

    monkeypatch.setattr("services.read_page.normalize_page", fake_normalize_page)

    markdown, attempts = asyncio.run(
        ReadPageService().read_with_trace("https://forum.cursor.com/t/composer-2-vs-auto-model-pricing/157665")
    )

    assert attempts[0].fetch_method == "camoufox"
    assert attempts[0].weak is False
    assert "Auto has flat-rate pricing" in markdown
