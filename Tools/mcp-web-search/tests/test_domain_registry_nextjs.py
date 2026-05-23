from __future__ import annotations

from core.registry.domain_registry import get_registry


def test_domain_registry_marks_cursor_as_nextjs_rsc() -> None:
    registry = get_registry()

    info = registry.lookup("https://cursor.com/help/account-and-billing/pricing")

    assert info.pattern == "cursor.com"
    assert info.method == "http"
    assert info.parsing_mode == "nextjs_rsc"
    assert registry.prefers_nextjs_rsc("https://cursor.com/help/account-and-billing/pricing") is True
