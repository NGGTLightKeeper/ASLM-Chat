from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from core.registry.trust_registry import (
    TrustRegistry,
    clear_trust_registry_cache,
    load_trust_registry,
    _load_merged_registry,
    _PROFILES_DIR,
)


@pytest.fixture(autouse=True)
def _fresh_trust_cache() -> None:
    clear_trust_registry_cache()
    yield
    clear_trust_registry_cache()


def _write_global(directory: Path, *, tiers: dict | None = None, blacklist: dict | None = None) -> None:
    payload: dict = {}
    if tiers is not None:
        payload["tiers"] = tiers
    if blacklist is not None:
        payload["blacklist"] = blacklist
    (directory / "_global.json").write_text(json.dumps(payload), encoding="utf-8")


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
        pytest.skip("trust_registry_profiles directory not present")
    paths = sorted(
        p
        for p in _PROFILES_DIR.glob("*.json")
        if p.name.lower() not in ("manifest.json", "_global.json")
    )
    if not paths:
        pytest.skip("no modular trust profiles migrated yet")
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data.get("profile"), str)
        assert isinstance(data.get("domains"), list)


def test_global_blacklist_and_tiers(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "trust_registry_profiles"
    profiles_dir.mkdir()
    _write_global(
        profiles_dir,
        tiers={"A": {"weight": 1.0, "label": "Authoritative"}},
        blacklist={"blocked_extensions": [".exe"], "blocked_domain_contains": [], "blocked_url_patterns": []},
    )

    tiers, blacklist, _ = load_trust_registry(profiles_dir=profiles_dir, legacy_path=tmp_path / "missing.json")
    assert tiers["A"]["weight"] == 1.0
    assert ".exe" in blacklist["blocked_extensions"]

    reg = TrustRegistry(profiles_dir=str(profiles_dir))
    assert reg.is_blacklisted("https://evil.com/file.exe")
    assert reg.get_weight("https://example.com") == 0.0


def test_merge_by_pattern_and_defaults(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "trust_registry_profiles"
    profiles_dir.mkdir()
    _write_global(
        profiles_dir,
        tiers={"A": {"weight": 1.0}, "B": {"weight": 0.75}},
        blacklist={"blocked_extensions": [], "blocked_domain_contains": [], "blocked_url_patterns": []},
    )

    _write_profile(
        profiles_dir,
        "alpha.json",
        profile="alpha",
        defaults={"tier": "B", "cat": "general"},
        domains=[
            {
                "pattern": "example.com",
                "aliases": ["www.example.com"],
                "class_affinity": {"general": 1.0, "technical": 0.9},
            },
        ],
    )
    _write_profile(
        profiles_dir,
        "beta.json",
        profile="beta",
        defaults={"tier": "C", "cat": "web"},
        domains=[
            {
                "pattern": "example.com",
                "aliases": ["m.example.com"],
                "tier": "A",
                "class_affinity": {"technical": 1.1, "academic": 1.2},
            },
        ],
    )

    _, _, merged = load_trust_registry(profiles_dir=profiles_dir, legacy_path=tmp_path / "missing.json")
    info = merged["example.com"]

    assert info.tier == "A"
    assert info.cat == "web"
    assert set(info.aliases) == {"www.example.com", "m.example.com"}
    assert info.class_affinity["technical"] == 1.1
    assert info.class_affinity["academic"] == 1.2
    assert info.class_affinity["general"] == 1.0


def test_defaults_applied_to_sparse_domain(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "trust_registry_profiles"
    profiles_dir.mkdir()
    _write_global(profiles_dir, tiers={"B": {"weight": 0.75}}, blacklist={})
    _write_profile(
        profiles_dir,
        "academic.json",
        profile="academic",
        defaults={"tier": "B", "cat": "science"},
        domains=[
            {
                "pattern": "arxiv.org",
                "class_affinity": {"academic": 1.0},
            },
        ],
    )

    info = load_trust_registry(profiles_dir=profiles_dir)[2]["arxiv.org"]
    assert info.tier == "B"
    assert info.cat == "science"
    assert info.class_affinity["academic"] == 1.0


def test_legacy_fallback_when_profiles_empty(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "trust_registry_profiles"
    profiles_dir.mkdir()
    (profiles_dir / "manifest.json").write_text(
        json.dumps({"version": 1, "profiles": []}),
        encoding="utf-8",
    )
    legacy = tmp_path / "trust_registry.json"
    legacy.write_text(
        json.dumps(
            {
                "tiers": {"C": {"weight": 0.45, "label": "Community"}},
                "domains": [{"pattern": "legacy.example", "tier": "C", "cat": "web"}],
                "blacklist": {"blocked_extensions": [".zip"], "blocked_domain_contains": [], "blocked_url_patterns": []},
            }
        ),
        encoding="utf-8",
    )

    tiers, blacklist, domains = load_trust_registry(profiles_dir=profiles_dir, legacy_path=legacy)
    assert "legacy.example" in domains
    assert domains["legacy.example"].tier == "C"
    assert tiers["C"]["weight"] == 0.45
    assert ".zip" in blacklist.get("blocked_extensions", [])


def test_profile_overrides_legacy_for_same_pattern(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "trust_registry_profiles"
    profiles_dir.mkdir()
    legacy = tmp_path / "trust_registry.json"
    legacy.write_text(
        json.dumps(
            {
                "domains": [{"pattern": "overlap.test", "tier": "C", "cat": "web"}],
            }
        ),
        encoding="utf-8",
    )
    _write_global(profiles_dir, tiers={"A": {"weight": 1.0}}, blacklist={})
    _write_profile(
        profiles_dir,
        "academic.json",
        profile="academic",
        domains=[{"pattern": "overlap.test", "tier": "A", "cat": "science"}],
    )

    info = load_trust_registry(profiles_dir=profiles_dir, legacy_path=legacy)[2]["overlap.test"]
    assert info.tier == "A"
    assert info.cat == "science"


def test_production_registry_loads_from_legacy_monolith() -> None:
    if not (ROOT / "core" / "registry" / "trust_registry.json").is_file():
        pytest.skip("production trust_registry.json missing")
    reg = TrustRegistry()
    assert reg.get_tier("https://arxiv.org/abs/1234") == "A"
    assert reg.get_weight("https://arxiv.org/abs/1234") == 1.0
    assert reg.is_blacklisted("https://pinterest.com/pin/1") is True


def test_loader_cache_returns_same_object(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "trust_registry_profiles"
    profiles_dir.mkdir()
    _write_profile(
        profiles_dir,
        "cached.json",
        profile="cached",
        domains=[{"pattern": "cache.test", "tier": "B"}],
    )
    _write_global(profiles_dir, tiers={"B": {"weight": 0.75}}, blacklist={})

    key_profiles = str(profiles_dir.resolve())
    missing_legacy = str((tmp_path / "no_legacy.json").resolve())
    a = _load_merged_registry(key_profiles, missing_legacy)
    b = _load_merged_registry(key_profiles, missing_legacy)
    assert a.loaded and b.loaded
    assert a is b
