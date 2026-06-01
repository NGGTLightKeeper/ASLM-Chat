# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio

from services.read_page import ReadPageService


# ReadPageService — registry-driven nextjs_rsc fast path without normalize_page.

def test_read_page_uses_registry_driven_nextjs_rsc_fast_path(monkeypatch) -> None:
    monkeypatch.setattr("services.read_page._cache.get_cached", lambda url: None)

    async def fake_fetch_race(*args, **kwargs) -> str | None:
        return """
        <html>
          <body>
            <script>self.__next_f.push([1,"10:[\\"$\\",\\"$Lheading\\",null,{\\"baseId\\":\\"pricing\\",\\"children\\":\\"Pricing and plans\\"}]\\n11:[\\"$\\",\\"p\\",null,{\\"children\\":\\"Model pricing\\"}]\\n12:[\\"$\\",\\"ul\\",null,{\\"children\\":[[\\"$\\",\\"li\\",null,{\\"children\\":\\"Auto\\"}],[\\"$\\",\\"li\\",null,{\\"children\\":\\"Premium\\"}]]}]\\n"])</script>
          </body>
        </html>
        """

    def fail_normalize(url: str, raw_html: str) -> str:
        raise AssertionError("normalize_page should not run for nextjs_rsc domains when RSC extraction succeeds")

    monkeypatch.setattr("services.read_page._fetch_race", fake_fetch_race)
    monkeypatch.setattr("services.read_page.normalize_page", fail_normalize)
    monkeypatch.setattr(
        "services.read_page._is_weak_extraction",
        lambda markdown, min_length: "Model pricing" not in markdown,
    )

    service = ReadPageService()
    markdown, attempts = asyncio.run(service.read_with_trace("https://cursor.com/help/account-and-billing/pricing"))

    assert attempts[0].fetch_method == "network_rsc"
    assert attempts[0].weak is False
    assert "## Pricing and plans" in markdown
    assert "Model pricing" in markdown
    assert "- Auto" in markdown
    assert "- Premium" in markdown
