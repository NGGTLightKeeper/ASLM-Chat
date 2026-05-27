from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.registry.domain_registry import (
    DomainRegistry,
    clear_domain_registry_cache,
    load_domain_registry,
    _load_merged_registry,
    _PROFILES_DIR,
)


@pytest.fixture(autouse=True)
def _fresh_registry_cache() -> None:
    clear_domain_registry_cache()
    yield
    clear_domain_registry_cache()


def _write_profile(
    directory: Path,
    name: str,
    *,
    profile: str,
    defaults: dict | None = None,
    domains: list[dict],
) -> None:
    payload: dict = {
        "profile": profile,
        "description": f"{profile} test profile",
        "domains": domains,
    }
    if defaults is not None:
        payload["defaults"] = defaults
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def test_all_production_profile_json_parse() -> None:
    if not _PROFILES_DIR.is_dir():
        pytest.skip("domain_profiles directory not present")
    paths = sorted(
        p for p in _PROFILES_DIR.glob("*.json") if p.name.lower() != "manifest.json"
    )
    if not paths:
        pytest.skip("no modular domain profiles migrated yet")
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data.get("profile"), str)
        assert isinstance(data.get("domains"), list)


def test_merge_by_pattern_and_defaults(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "domain_profiles"
    profiles_dir.mkdir()

    _write_profile(
        profiles_dir,
        "alpha.json",
        profile="alpha",
        defaults={"tier": "moderate", "method": "http", "rps": 1.0, "burst": 3, "base_weight": 1.0},
        domains=[
            {
                "pattern": "example.com",
                "aliases": ["www.example.com"],
                "class_weights": {"general": 1.0, "technical": 1.1},
            },
        ],
    )
    _write_profile(
        profiles_dir,
        "beta.json",
        profile="beta",
        defaults={"tier": "friendly", "method": "json_api", "rps": 2.0, "burst": 5},
        domains=[
            {
                "pattern": "example.com",
                "aliases": ["m.example.com"],
                "tier": "hardened",
                "class_weights": {"technical": 1.3, "academic": 1.2},
                "hard_demotions": {"shopping": 0.4},
            },
        ],
    )

    merged = load_domain_registry(profiles_dir=profiles_dir, legacy_path=tmp_path / "missing.json")
    info = merged["example.com"]

    assert info.tier == "hardened"
    assert info.method == "json_api"
    assert info.rps == 2.0
    assert info.burst == 5
    assert set(info.aliases) == {"www.example.com", "m.example.com"}
    assert info.class_weights["technical"] == 1.3
    assert info.class_weights["academic"] == 1.2
    assert info.class_weights["general"] == 1.0
    assert info.hard_demotions["shopping"] == 0.4


def test_defaults_applied_to_sparse_domain(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "domain_profiles"
    profiles_dir.mkdir()
    _write_profile(
        profiles_dir,
        "academic.json",
        profile="academic",
        defaults={
            "base_weight": 1.0,
            "tier": "moderate",
            "method": "http",
            "rps": 1.0,
            "burst": 3,
        },
        domains=[
            {
                "pattern": "arxiv.org",
                "topics": ["academic"],
                "class_weights": {"academic": 1.45},
            },
        ],
    )

    info = load_domain_registry(profiles_dir=profiles_dir)["arxiv.org"]
    assert info.tier == "moderate"
    assert info.method == "http"
    assert info.base_weight == 1.0
    assert info.class_weights["academic"] == 1.45


def test_class_weights_accessible_via_registry_lookup(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "domain_profiles"
    profiles_dir.mkdir()
    _write_profile(
        profiles_dir,
        "one.json",
        profile="one",
        domains=[
            {
                "pattern": "cursor.com",
                "parsing_mode": "nextjs_rsc",
                "class_weights": {"technical": 1.25},
            },
        ],
    )

    reg = DomainRegistry(profiles_dir=str(profiles_dir))
    info = reg.lookup("https://cursor.com/docs")
    assert info.class_weights["technical"] == 1.25
    assert info.parsing_mode == "nextjs_rsc"


def test_json_api_hint_is_exposed_as_access_strategy_endpoint(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "domain_profiles"
    profiles_dir.mkdir()
    _write_profile(
        profiles_dir,
        "api.json",
        profile="api",
        domains=[
            {
                "pattern": "api.example",
                "method": "json_api",
                "json_api_hint": "https://api.example/search?q=<q>",
            },
        ],
    )

    strategy = DomainRegistry(profiles_dir=str(profiles_dir)).resolve_access_strategy("https://api.example/docs")

    assert strategy.method == "json_api"
    assert strategy.endpoint_url == "https://api.example/search?q=<q>"


def test_ncbi_host_does_not_use_pubmed_json_api() -> None:
    registry = DomainRegistry()

    pubmed = registry.resolve_access_strategy("https://pubmed.ncbi.nlm.nih.gov/123456/")
    pmc = registry.resolve_access_strategy("https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123/")

    assert pubmed.method == "json_api"
    assert "db=pubmed" in pubmed.endpoint_url
    assert pmc.domain == "ncbi.nlm.nih.gov"
    assert pmc.method == "http"


def test_loader_cache_returns_same_object(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "domain_profiles"
    profiles_dir.mkdir()
    _write_profile(
        profiles_dir,
        "cached.json",
        profile="cached",
        domains=[{"pattern": "cache.test"}],
    )

    key_profiles = str(profiles_dir.resolve())
    missing_legacy = str((tmp_path / "no_legacy.json").resolve())
    a, loaded_a, _ = _load_merged_registry(key_profiles, missing_legacy)
    b, loaded_b, _ = _load_merged_registry(key_profiles, missing_legacy)
    assert loaded_a and loaded_b
    assert a is b


def test_legacy_fallback_when_profiles_empty(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "domain_profiles"
    profiles_dir.mkdir()
    (profiles_dir / "manifest.json").write_text(
        json.dumps({"version": 1, "profiles": []}),
        encoding="utf-8",
    )
    legacy = tmp_path / "domain_registry.json"
    legacy.write_text(
        json.dumps(
            {
                "domains": [
                    {"pattern": "legacy.example", "tier": "friendly", "method": "http", "topics": ["general"]},
                ],
            }
        ),
        encoding="utf-8",
    )

    merged = load_domain_registry(profiles_dir=profiles_dir, legacy_path=legacy)
    assert "legacy.example" in merged
    assert merged["legacy.example"].tier == "friendly"


def test_profile_overrides_legacy_for_same_pattern(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "domain_profiles"
    profiles_dir.mkdir()
    legacy = tmp_path / "domain_registry.json"
    legacy.write_text(
        json.dumps(
            {
                "domains": [
                    {"pattern": "overlap.test", "tier": "fortress", "method": "skip", "topics": ["shopping"]},
                ],
            }
        ),
        encoding="utf-8",
    )
    _write_profile(
        profiles_dir,
        "shop.json",
        profile="shopping",
        domains=[
            {"pattern": "overlap.test", "tier": "friendly", "method": "http", "class_weights": {"shopping": 1.5}},
        ],
    )

    info = load_domain_registry(profiles_dir=profiles_dir, legacy_path=legacy)["overlap.test"]
    assert info.tier == "friendly"
    assert info.method == "http"
    assert info.class_weights["shopping"] == 1.5
