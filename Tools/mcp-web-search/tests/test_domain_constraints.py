from __future__ import annotations

from core.query.domain_constraints import build_provider_query, parse_domain_constraints


def test_user_boolean_or_is_preserved_with_site_constraint() -> None:
    constraints = parse_domain_constraints("foo OR bar site:reddit.com")

    assert constraints.clean_query == "foo OR bar"
    assert build_provider_query("foo OR bar site:reddit.com", constraints) == "site:reddit.com foo OR bar"


def test_domain_connector_or_is_removed_when_it_becomes_orphaned() -> None:
    constraints = parse_domain_constraints("site:reddit.com OR site:stackoverflow.com oauth error")

    assert constraints.clean_query == "oauth error"
    assert constraints.include_domains == ["reddit.com", "stackoverflow.com"]


def test_exclude_only_site_constraint_is_sent_to_provider() -> None:
    constraints = parse_domain_constraints("foo -site:wikipedia.org")

    assert constraints.clean_query == "foo"
    assert constraints.exclude_domains == ["wikipedia.org"]
    assert build_provider_query("foo -site:wikipedia.org", constraints) == "foo -site:wikipedia.org"

