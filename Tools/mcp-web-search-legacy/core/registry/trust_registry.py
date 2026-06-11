# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .config import TRUST_PROFILES_DIR, TRUST_REGISTRY_PATH

logger = logging.getLogger("core.registry.trust_registry")

_REGISTRY_DIR = Path(__file__).resolve().parent
_PROFILES_DIR = TRUST_PROFILES_DIR
_MANIFEST_NAME = "manifest.json"
_GLOBAL_NAME = "_global.json"
_SKIP_PROFILE_NAMES = frozenset({_MANIFEST_NAME.lower(), _GLOBAL_NAME.lower()})
_LEGACY_CANDIDATES = (
    TRUST_REGISTRY_PATH,
    _REGISTRY_DIR / "config" / "trust_registry.json",
)

_PROFILE_REQUIRED_KEYS = frozenset({"profile", "domains"})

# Merge semantics (documented for operators and tests):
# - Duplicate pattern across profile files: later file wins for scalar fields; aliases are unioned.
# - class_affinity: per-class maximum (strongest affinity retained).
# - Legacy trust_registry.json is loaded first as a base; profile entries override per pattern.
# - tiers and blacklist come from trust_registry_profiles/_global.json when present, else legacy monolith.


# Trust tier and class affinity for one domain pattern.
@dataclass
class TrustDomainEntry:
    pattern: str
    tier: str = "C"
    cat: str = ""
    aliases: List[str] = field(default_factory=list)
    class_affinity: Dict[str, float] = field(default_factory=dict)
    notes: str = ""

    # Serialize entry for legacy-compatible domain list output.
    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "tier": self.tier,
            "cat": self.cat,
            "aliases": list(self.aliases),
            "class_affinity": dict(self.class_affinity),
            "notes": self.notes,
        }


# True when host equals domain or is a subdomain of it.
def _is_host_match(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


# Merge class_affinity maps keeping per-class maximum.
def _merge_float_maps(existing: Dict[str, float], incoming: Dict[str, float]) -> Dict[str, float]:
    merged = dict(existing)
    for key, value in incoming.items():
        k = str(key).strip().lower()
        if not k:
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        merged[k] = max(merged.get(k, 0.0), v) if k in merged else v
    return merged


# Build TrustDomainEntry from one profile or legacy JSON entry.
def _entry_from_dict(entry: dict[str, Any], defaults: dict[str, Any]) -> Optional[TrustDomainEntry]:
    pattern = str(entry.get("pattern") or defaults.get("pattern") or "").strip().lower()
    if not pattern:
        return None

    # Prefer entry value, else defaults, for one field key.
    def _pick(key: str, default: Any = "") -> Any:
        if key in entry and entry[key] is not None:
            return entry[key]
        return defaults.get(key, default)

    aliases_raw = _pick("aliases") or []
    if not isinstance(aliases_raw, list):
        aliases_raw = []

    affinity_raw = _pick("class_affinity") or {}
    if not isinstance(affinity_raw, dict):
        affinity_raw = {}

    return TrustDomainEntry(
        pattern=pattern,
        tier=str(_pick("tier", "C")).upper(),
        cat=str(_pick("cat") or ""),
        aliases=[a.lower() for a in aliases_raw if str(a).strip()],
        class_affinity={
            str(k).lower(): float(v)
            for k, v in affinity_raw.items()
            if str(k).strip()
        },
        notes=str(_pick("notes") or ""),
    )


# Overlay wins scalars; aliases unioned; class_affinity max-merged.
def _merge_trust_entry(base: TrustDomainEntry, overlay: TrustDomainEntry) -> TrustDomainEntry:
    return TrustDomainEntry(
        pattern=base.pattern,
        tier=overlay.tier,
        cat=overlay.cat or base.cat,
        aliases=sorted(set(base.aliases) | set(overlay.aliases)),
        class_affinity=_merge_float_maps(base.class_affinity, overlay.class_affinity),
        notes=overlay.notes or base.notes,
    )


# Validate one trust profile JSON file structure.
def _validate_profile_file(path: Path, data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: root must be object")
    missing = _PROFILE_REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"{path.name}: profile missing keys {missing}")
    if not isinstance(data.get("domains"), list):
        raise ValueError(f"{path.name}: 'domains' must be a list")
    defaults = data.get("defaults")
    if defaults is not None and not isinstance(defaults, dict):
        raise ValueError(f"{path.name}: 'defaults' must be an object")
    for i, entry in enumerate(data["domains"]):
        if not isinstance(entry, dict):
            raise ValueError(f"{path.name}: domains[{i}] must be object")
        if "_section" in entry:
            continue
        if "pattern" not in entry:
            raise ValueError(f"{path.name}: domains[{i}] missing 'pattern'")


# Profile JSON load order from manifest.json then remaining *.json files.
def _profile_load_order(profiles_dir: Path) -> List[Path]:
    manifest_path = profiles_dir / _MANIFEST_NAME
    ordered: List[Path] = []
    seen: set[str] = set()

    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            for name in manifest.get("profiles") or []:
                stem = str(name).strip()
                if not stem:
                    continue
                filename = stem if stem.endswith(".json") else f"{stem}.json"
                path = profiles_dir / filename
                if path.is_file() and path.name.lower() not in _SKIP_PROFILE_NAMES:
                    ordered.append(path)
                    seen.add(path.name.lower())
        except Exception as exc:
            logger.warning("Invalid trust profile manifest: %s", exc)

    for path in sorted(profiles_dir.glob("*.json")):
        if path.name.lower() in _SKIP_PROFILE_NAMES:
            continue
        if path.name.lower() not in seen:
            ordered.append(path)
    return ordered


# Load tiers and blacklist from trust_registry_profiles/_global.json.
def _load_global_config(profiles_dir: Path) -> tuple[dict[str, dict], dict]:
    global_path = profiles_dir / _GLOBAL_NAME
    if global_path.is_file():
        try:
            data = json.loads(global_path.read_text(encoding="utf-8-sig"))
            tiers = data.get("tiers") if isinstance(data.get("tiers"), dict) else {}
            blacklist = data.get("blacklist") if isinstance(data.get("blacklist"), dict) else {}
            return tiers, blacklist
        except Exception as exc:
            logger.error("Failed to load trust global config %s: %s", global_path, exc)
    return {}, {}


# Load domain patterns from legacy monolithic trust_registry.json.
def _load_legacy_domains(path: Path) -> Dict[str, TrustDomainEntry]:
    by_pattern: Dict[str, TrustDomainEntry] = {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        logger.error("Failed to load legacy trust registry %s: %s", path, exc)
        return by_pattern

    for entry in data.get("domains", []):
        if not isinstance(entry, dict) or "_section" in entry:
            continue
        info = _entry_from_dict(entry, {})
        if info is None:
            continue
        by_pattern[info.pattern] = info
    return by_pattern


# Read tiers and blacklist from legacy monolith without loading domains.
def _legacy_tiers_and_blacklist(path: Path) -> tuple[dict[str, dict], dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}, {}
    tiers = data.get("tiers") if isinstance(data.get("tiers"), dict) else {}
    blacklist = data.get("blacklist") if isinstance(data.get("blacklist"), dict) else {}
    return tiers, blacklist


# Load and merge domain patterns from trust_registry_profiles/ JSON files.
def _load_profile_domains(profiles_dir: Path) -> Dict[str, TrustDomainEntry]:
    by_pattern: Dict[str, TrustDomainEntry] = {}
    if not profiles_dir.is_dir():
        return by_pattern

    for path in _profile_load_order(profiles_dir):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            _validate_profile_file(path, data)
        except Exception as exc:
            logger.error("Failed to load trust profile %s: %s", path, exc)
            continue

        defaults = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}
        for entry in data.get("domains", []):
            if not isinstance(entry, dict) or "_section" in entry:
                continue
            info = _entry_from_dict(entry, defaults)
            if info is None:
                continue
            if info.pattern in by_pattern:
                by_pattern[info.pattern] = _merge_trust_entry(by_pattern[info.pattern], info)
            else:
                by_pattern[info.pattern] = info

    return by_pattern


# Resolve legacy monolith path from explicit arg or known candidates.
def _resolve_legacy_path(explicit: Optional[str]) -> Optional[Path]:
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    for candidate in _LEGACY_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


# Cached merge result: tiers, blacklist, domains, load metadata.
@dataclass
class _MergedTrustData:
    tiers: dict[str, dict]
    blacklist: dict
    domains: Dict[str, TrustDomainEntry]
    loaded: bool
    source: str


# Merge legacy monolith, _global.json, and profile domain entries (cached).
@lru_cache(maxsize=8)
def _load_merged_registry(
    profiles_dir_str: str,
    legacy_path_str: Optional[str],
) -> _MergedTrustData:
    profiles_dir = Path(profiles_dir_str)
    legacy_path = Path(legacy_path_str) if legacy_path_str else _resolve_legacy_path(None)

    tiers: dict[str, dict] = {}
    blacklist: dict = {}
    by_pattern: Dict[str, TrustDomainEntry] = {}
    source = "empty"

    if legacy_path and legacy_path.is_file():
        by_pattern = _load_legacy_domains(legacy_path)
        legacy_tiers, legacy_blacklist = _legacy_tiers_and_blacklist(legacy_path)
        tiers = legacy_tiers
        blacklist = legacy_blacklist
        source = f"legacy:{legacy_path.name}"

    global_tiers, global_blacklist = _load_global_config(profiles_dir)
    if global_tiers:
        tiers = global_tiers
    if global_blacklist:
        blacklist = global_blacklist
    if global_tiers or global_blacklist:
        source = f"{source}+global" if source != "empty" else "global"

    profile_domains = _load_profile_domains(profiles_dir)
    if profile_domains:
        for pattern, info in profile_domains.items():
            if pattern in by_pattern:
                by_pattern[pattern] = _merge_trust_entry(by_pattern[pattern], info)
            else:
                by_pattern[pattern] = info
        source = f"{source}+profiles" if source != "empty" else "profiles"

    loaded = bool(by_pattern or tiers or blacklist)
    return _MergedTrustData(
        tiers=tiers,
        blacklist=blacklist,
        domains=by_pattern,
        loaded=loaded,
        source=source,
    )


# Clear cached merged registry and singleton (for tests).
def clear_trust_registry_cache() -> None:
    _load_merged_registry.cache_clear()
    global _instance
    _instance = None


# Return (tiers, blacklist, domains_by_pattern) from merged sources.
def load_trust_registry(
    profiles_dir: Optional[Path | str] = None,
    legacy_path: Optional[Path | str] = None,
) -> tuple[dict[str, dict], dict, Dict[str, TrustDomainEntry]]:
    pdir = Path(profiles_dir) if profiles_dir else _PROFILES_DIR
    legacy = Path(legacy_path) if legacy_path else _resolve_legacy_path(None)
    merged = _load_merged_registry(
        str(pdir.resolve()),
        str(legacy.resolve()) if legacy else None,
    )
    return merged.tiers, merged.blacklist, dict(merged.domains)


# Load trust tiers and blacklist from modular profile JSONs or legacy monolith.
class TrustRegistry:

    # Load merged trust data from profiles, global config, and optional legacy file.
    def __init__(
        self,
        path: Optional[str] = None,
        profiles_dir: Optional[str] = None,
    ) -> None:
        pdir = Path(profiles_dir) if profiles_dir else _PROFILES_DIR
        legacy = _resolve_legacy_path(path)

        merged = _load_merged_registry(
            str(pdir.resolve()),
            str(legacy.resolve()) if legacy else None,
        )

        self.tiers: dict[str, dict] = merged.tiers
        self.blacklist: dict = merged.blacklist
        self.domains: list[dict] = [e.as_dict() for e in merged.domains.values()]
        self._loaded = merged.loaded
        self._source = merged.source

        self._lookup: dict[str, TrustDomainEntry] = {}
        for info in merged.domains.values():
            self._lookup[info.pattern] = info
            for alias in info.aliases:
                self._lookup[alias] = info

        if not self._loaded:
            logger.warning("Trust registry empty - no profiles, global config, or legacy file found")
        else:
            logger.info(
                "TrustRegistry loaded: %s patterns (%s lookup keys) from %s",
                len(merged.domains),
                len(self._lookup),
                self._source,
            )

    # Return trust entry for URL host if pattern matches.
    def get_entry(self, url: str) -> Optional[TrustDomainEntry]:
        netloc = urlparse(url).netloc.lower()
        for pattern, entry in self._lookup.items():
            if netloc == pattern or netloc.endswith("." + pattern):
                return entry
        return None

    # Return trust tier letter (A/B/C) for URL or None.
    def get_tier(self, url: str) -> Optional[str]:
        entry = self.get_entry(url)
        return entry.tier if entry is not None else None

    # Return numeric tier weight from tiers config for URL.
    def get_weight(self, url: str) -> float:
        tier = self.get_tier(url)
        if not tier:
            return 0.0

        return self.tiers.get(tier, {}).get("weight", 0.0)

    # True when URL matches extension, domain, or pattern blacklist rules.
    def is_blacklisted(self, url: str) -> bool:
        url_lower = url.lower()
        netloc = urlparse(url).netloc.lower()

        for extension in self.blacklist.get("blocked_extensions", []):
            if url_lower.endswith(extension):
                return True

        for blocked_domain in self.blacklist.get("blocked_domain_contains", []):
            if blocked_domain in netloc:
                return True

        trusted_domains = {
            "github.com",
            "huggingface.co",
            "gitlab.com",
            "arxiv.org",
            "stackoverflow.com",
        }
        if not any(_is_host_match(netloc, domain) for domain in trusted_domains):
            for pattern in self.blacklist.get("blocked_url_patterns", []):
                if pattern in url_lower:
                    return True

        return False

    # Keep search results whose URL tier is in allowed_tiers.
    def filter_results(self, results: list, allowed_tiers: set[str]) -> list:
        filtered = []
        for result in results:
            url = result.url if hasattr(result, "url") else result.get("url", "")
            tier = self.get_tier(url)
            if tier and tier in allowed_tiers:
                filtered.append(result)

        return filtered


_instance: Optional[TrustRegistry] = None


# Shared TrustRegistry singleton.
def get_trust_registry() -> TrustRegistry:
    global _instance

    if _instance is None:
        _instance = TrustRegistry()

    return _instance
