# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .config import DOMAIN_PROFILES_DIR, DOMAIN_REGISTRY_PATH
from .endpoint_overlay import EndpointStrategy, get_endpoint_overlay, normalize_domain

logger = logging.getLogger("core.registry.domain_registry")

_REGISTRY_DIR = Path(__file__).resolve().parent
_PROFILES_DIR = DOMAIN_PROFILES_DIR
_MANIFEST_NAME = "manifest.json"
_LEGACY_CANDIDATES = (
    DOMAIN_REGISTRY_PATH,
    _REGISTRY_DIR / "config" / "domain_registry.json",
    _REGISTRY_DIR.parent / "config" / "domain_registry.json",
    _REGISTRY_DIR.parent / "domain_registry.json",
)

_PROFILE_REQUIRED_KEYS = frozenset({"profile", "domains"})

# Merge semantics (documented for operators and tests):
# - Duplicate pattern across profile files: later file wins for scalar fields; aliases are unioned.
# - class_weights: per-class maximum (strongest boost retained).
# - hard_demotions: per-class minimum (strongest demotion retained).
# - path_weights: concatenated; same path_prefix merges class_weights with max.
# - Legacy monolithic domain_registry.json is loaded first as a base; profile entries override per pattern.


# Path-prefix class weight overrides for a domain pattern.
@dataclass
class PathWeight:
    path_prefix: str
    class_weights: Dict[str, float] = field(default_factory=dict)


# Static domain metadata: tier, fetch method, weights, and aliases.
@dataclass
class DomainInfo:
    pattern: str
    tier: str = "unknown"  # friendly / moderate / hardened / fortress
    method: str = "http"  # http / xml_feed / json_api / nodriver / camoufox / official_api / skip
    rps: float = 1.0
    burst: int = 3
    aliases: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    source_types: List[str] = field(default_factory=list)
    base_weight: float = 1.0
    class_weights: Dict[str, float] = field(default_factory=dict)
    hard_demotions: Dict[str, float] = field(default_factory=dict)
    path_weights: List[PathWeight] = field(default_factory=list)
    feed_prefix: Optional[str] = None
    json_api_hint: Optional[str] = None
    official_api: Optional[str] = None
    waf: Optional[str] = None
    rate_limit_headers: List[str] = field(default_factory=list)
    notes: str = ""
    response_time_ms: Optional[int] = None
    try_preview_bot: bool = False
    parsing_mode: str = ""


# Resolved fetch strategy combining static registry and endpoint overlay.
@dataclass
class AccessStrategy:
    source: str = "default"
    method: str = "http"
    domain: str = ""
    tier: str = "unknown"
    endpoint_url: str = ""
    rewritten_url: str = ""
    scope: str = "domain"
    path_pattern: str = ""
    transform_kind: str = ""
    seed_urls: List[str] = field(default_factory=list)
    method_hint: str = "http"
    response_time_ms: Optional[int] = None


_DEFAULT_INFO = DomainInfo(
    pattern="*",
    tier="unknown",
    method="http",
    rps=1.0,
    burst=3,
    topics=["general"],
    notes="Unknown domain - default settings",
)


# Merge float maps with max or min per key.
def _merge_float_maps(existing: Dict[str, float], incoming: Dict[str, float], *, op: str) -> Dict[str, float]:
    merged = dict(existing)
    for key, value in incoming.items():
        k = str(key).strip().lower()
        if not k:
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if k not in merged:
            merged[k] = v
        elif op == "max":
            merged[k] = max(merged[k], v)
        elif op == "min":
            merged[k] = min(merged[k], v)
    return merged


# Merge path_weights lists; same prefix merges class_weights with max.
def _merge_path_weights(existing: List[PathWeight], incoming: List[PathWeight]) -> List[PathWeight]:
    by_prefix: Dict[str, PathWeight] = {pw.path_prefix: pw for pw in existing}
    for pw in incoming:
        if pw.path_prefix in by_prefix:
            by_prefix[pw.path_prefix] = PathWeight(
                path_prefix=pw.path_prefix,
                class_weights=_merge_float_maps(by_prefix[pw.path_prefix].class_weights, pw.class_weights, op="max"),
            )
        else:
            by_prefix[pw.path_prefix] = pw
    return sorted(by_prefix.values(), key=lambda x: x.path_prefix)


# Parse path_weights array from JSON into PathWeight objects.
def _parse_path_weights(raw: Any) -> List[PathWeight]:
    if not isinstance(raw, list):
        return []
    result: List[PathWeight] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        prefix = str(item.get("path_prefix") or "").strip()
        if not prefix:
            continue
        weights = item.get("class_weights") or {}
        if not isinstance(weights, dict):
            weights = {}
        result.append(
            PathWeight(
                path_prefix=prefix,
                class_weights={str(k).lower(): float(v) for k, v in weights.items()},
            )
        )
    return result


# Build DomainInfo from one profile or legacy JSON entry.
def _domain_from_dict(entry: dict[str, Any], defaults: dict[str, Any]) -> Optional[DomainInfo]:
    pattern = str(entry.get("pattern") or defaults.get("pattern") or "").strip().lower()
    if not pattern:
        return None

    # Prefer entry value, else defaults, for one field key.
    def _pick(key: str, default: Any = None) -> Any:
        if key in entry and entry[key] is not None:
            return entry[key]
        return defaults.get(key, default)

    topics = entry.get("topics") if "topics" in entry else defaults.get("topics")
    if not isinstance(topics, list):
        topics = []
    source_types = entry.get("source_types") if "source_types" in entry else defaults.get("source_types")
    if not isinstance(source_types, list):
        source_types = []

    response_raw = _pick("response_time_ms")
    response_time_ms: Optional[int] = None
    if response_raw is not None:
        try:
            response_time_ms = int(response_raw)
        except (TypeError, ValueError):
            response_time_ms = None

    class_weights_raw = _pick("class_weights") or {}
    hard_demotions_raw = _pick("hard_demotions") or {}
    path_weights_raw = entry.get("path_weights") if "path_weights" in entry else defaults.get("path_weights")

    return DomainInfo(
        pattern=pattern,
        tier=str(_pick("tier", "unknown")).lower(),
        method=str(_pick("method", "http")).lower(),
        rps=float(_pick("rps", 1.0) or 0.0),
        burst=int(_pick("burst", 3) or 0),
        aliases=[a.lower() for a in (_pick("aliases") or []) if str(a).strip()],
        topics=[str(t).lower() for t in topics if str(t).strip()],
        source_types=[str(t).lower() for t in source_types if str(t).strip()],
        base_weight=float(_pick("base_weight", 1.0) or 1.0),
        class_weights={
            str(k).lower(): float(v)
            for k, v in (class_weights_raw if isinstance(class_weights_raw, dict) else {}).items()
        },
        hard_demotions={
            str(k).lower(): float(v)
            for k, v in (hard_demotions_raw if isinstance(hard_demotions_raw, dict) else {}).items()
        },
        path_weights=_parse_path_weights(path_weights_raw),
        feed_prefix=_pick("feed_prefix"),
        json_api_hint=_pick("json_api_hint"),
        official_api=_pick("official_api"),
        waf=_pick("waf"),
        rate_limit_headers=list(_pick("rate_limit_headers") or []),
        notes=str(_pick("notes") or ""),
        response_time_ms=response_time_ms,
        try_preview_bot=bool(_pick("try_preview_bot", False)),
        parsing_mode=str(_pick("parsing_mode") or "").strip().lower(),
    )


# Merge two entries for the same pattern; overlay wins scalars, maps merge per policy.
def _merge_domain_info(base: DomainInfo, overlay: DomainInfo) -> DomainInfo:
    topics = overlay.topics or base.topics
    merged = DomainInfo(
        pattern=base.pattern,
        tier=overlay.tier,
        method=overlay.method,
        rps=overlay.rps,
        burst=overlay.burst,
        aliases=sorted(set(base.aliases) | set(overlay.aliases)),
        topics=topics if topics else ["general"],
        source_types=overlay.source_types or base.source_types,
        base_weight=overlay.base_weight,
        class_weights=_merge_float_maps(base.class_weights, overlay.class_weights, op="max"),
        hard_demotions=_merge_float_maps(base.hard_demotions, overlay.hard_demotions, op="min"),
        path_weights=_merge_path_weights(base.path_weights, overlay.path_weights),
        feed_prefix=overlay.feed_prefix or base.feed_prefix,
        json_api_hint=overlay.json_api_hint or base.json_api_hint,
        official_api=overlay.official_api or base.official_api,
        waf=overlay.waf or base.waf,
        rate_limit_headers=overlay.rate_limit_headers or base.rate_limit_headers,
        notes=overlay.notes or base.notes,
        response_time_ms=overlay.response_time_ms if overlay.response_time_ms is not None else base.response_time_ms,
        try_preview_bot=overlay.try_preview_bot or base.try_preview_bot,
        parsing_mode=overlay.parsing_mode or base.parsing_mode,
    )
    return merged


# Validate one domain profile JSON file structure.
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
                if path.is_file() and path.name != _MANIFEST_NAME:
                    ordered.append(path)
                    seen.add(path.name.lower())
        except Exception as exc:
            logger.warning("Invalid domain profile manifest: %s", exc)

    for path in sorted(profiles_dir.glob("*.json")):
        if path.name.lower() == _MANIFEST_NAME.lower():
            continue
        if path.name.lower() not in seen:
            ordered.append(path)
    return ordered


# Load domain patterns from legacy monolithic domain_registry.json.
def _load_legacy_domains(path: Path) -> Dict[str, DomainInfo]:
    by_pattern: Dict[str, DomainInfo] = {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        logger.error("Failed to load legacy domain registry %s: %s", path, exc)
        return by_pattern

    for entry in data.get("domains", []):
        if not isinstance(entry, dict) or "_section" in entry:
            continue
        info = _domain_from_dict(entry, {})
        if info is None:
            continue
        by_pattern[info.pattern] = info
    return by_pattern


# Load and merge domain patterns from domain_profiles/ JSON files.
def _load_profile_domains(profiles_dir: Path) -> Dict[str, DomainInfo]:
    by_pattern: Dict[str, DomainInfo] = {}
    if not profiles_dir.is_dir():
        return by_pattern

    for path in _profile_load_order(profiles_dir):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            _validate_profile_file(path, data)
        except Exception as exc:
            logger.error("Failed to load domain profile %s: %s", path, exc)
            continue

        defaults = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}
        for entry in data.get("domains", []):
            if not isinstance(entry, dict) or "_section" in entry:
                continue
            info = _domain_from_dict(entry, defaults)
            if info is None:
                continue
            if info.pattern in by_pattern:
                by_pattern[info.pattern] = _merge_domain_info(by_pattern[info.pattern], info)
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


# Merge legacy monolith with profile domain entries (cached).
@lru_cache(maxsize=8)
def _load_merged_registry(
    profiles_dir_str: str,
    legacy_path_str: Optional[str],
) -> tuple[Dict[str, DomainInfo], bool, str]:
    profiles_dir = Path(profiles_dir_str)
    legacy_path = Path(legacy_path_str) if legacy_path_str else _resolve_legacy_path(None)

    by_pattern: Dict[str, DomainInfo] = {}
    source = "empty"

    if legacy_path and legacy_path.is_file():
        by_pattern = _load_legacy_domains(legacy_path)
        source = f"legacy:{legacy_path.name}"

    profile_domains = _load_profile_domains(profiles_dir)
    if profile_domains:
        for pattern, info in profile_domains.items():
            if pattern in by_pattern:
                by_pattern[pattern] = _merge_domain_info(by_pattern[pattern], info)
            else:
                by_pattern[pattern] = info
        source = f"{source}+profiles" if by_pattern else "profiles"

    if not by_pattern:
        loaded = False
    else:
        loaded = True

    return by_pattern, loaded, source


# Clear cached merged registry and singleton (for tests).
def clear_domain_registry_cache() -> None:
    _load_merged_registry.cache_clear()
    global _registry
    _registry = None


# Return merged domain entries keyed by pattern.
def load_domain_registry(
    profiles_dir: Optional[Path | str] = None,
    legacy_path: Optional[Path | str] = None,
) -> Dict[str, DomainInfo]:
    pdir = Path(profiles_dir) if profiles_dir else _PROFILES_DIR
    legacy = Path(legacy_path) if legacy_path else _resolve_legacy_path(None)
    by_pattern, _, _ = _load_merged_registry(
        str(pdir.resolve()),
        str(legacy.resolve()) if legacy else None,
    )
    return dict(by_pattern)


# Resolve domain metadata from static registry and dynamic endpoint overlay.
class DomainRegistry:

    # Load merged registry from profiles dir and optional legacy monolith.
    def __init__(
        self,
        config_path: Optional[str] = None,
        profiles_dir: Optional[str] = None,
    ):
        self._domains: Dict[str, DomainInfo] = {}
        self._loaded = False
        self._source = "empty"

        pdir = Path(profiles_dir) if profiles_dir else _PROFILES_DIR
        legacy = _resolve_legacy_path(config_path)

        by_pattern, loaded, source = _load_merged_registry(
            str(pdir.resolve()),
            str(legacy.resolve()) if legacy else None,
        )
        self._source = source
        self._register_patterns(by_pattern)
        self._loaded = loaded

        if not self._loaded:
            logger.warning("Domain registry empty - no profiles or legacy file found")

    # Register patterns and aliases into lookup map.
    def _register_patterns(self, by_pattern: Dict[str, DomainInfo]) -> None:
        self._domains.clear()
        for info in by_pattern.values():
            self._domains[info.pattern] = info
            for alias in info.aliases:
                self._domains[alias] = info
        if loaded_count := len(by_pattern):
            logger.info(
                "DomainRegistry loaded: %s unique patterns (%s lookup keys) from %s",
                loaded_count,
                len(self._domains),
                self._source,
            )

    # Normalize URL or host string to bare domain.
    def _extract_domain(self, url_or_domain: str) -> str:
        return normalize_domain(url_or_domain)

    # Lookup static DomainInfo without endpoint overlay.
    def _lookup_static(self, url_or_domain: str) -> DomainInfo:
        domain = self._extract_domain(url_or_domain)
        if not domain:
            return _DEFAULT_INFO

        if domain in self._domains:
            return self._domains[domain]

        parts = domain.split(".")
        for i in range(1, len(parts)):
            parent = ".".join(parts[i:])
            if parent in self._domains:
                return self._domains[parent]

        return _DEFAULT_INFO

    # Build DomainInfo from static entry plus validated overlay strategy.
    def _overlay_to_info(self, url_or_domain: str, overlay: EndpointStrategy) -> DomainInfo:
        static_info = self._lookup_static(url_or_domain)
        return DomainInfo(
            pattern=overlay.domain,
            tier=static_info.tier,
            method=overlay.method,
            rps=static_info.rps,
            burst=static_info.burst,
            aliases=list(static_info.aliases),
            topics=list(static_info.topics),
            source_types=list(static_info.source_types),
            base_weight=static_info.base_weight,
            class_weights=dict(static_info.class_weights),
            hard_demotions=dict(static_info.hard_demotions),
            path_weights=list(static_info.path_weights),
            feed_prefix=static_info.feed_prefix,
            json_api_hint=static_info.json_api_hint,
            official_api=static_info.official_api,
            waf=static_info.waf,
            rate_limit_headers=list(static_info.rate_limit_headers),
            notes=static_info.notes,
            response_time_ms=static_info.response_time_ms,
            try_preview_bot=static_info.try_preview_bot,
            parsing_mode=static_info.parsing_mode,
        )

    # Return DomainInfo preferring endpoint overlay when validated.
    def lookup(self, url_or_domain: str) -> DomainInfo:
        overlay = get_endpoint_overlay().lookup_validated(self._extract_domain(url_or_domain), url_or_domain)
        if overlay is not None:
            return self._overlay_to_info(url_or_domain, overlay)
        return self._lookup_static(url_or_domain)

    # Resolve fetch strategy from overlay or static registry entry.
    def resolve_access_strategy(self, url_or_domain: str) -> AccessStrategy:
        domain = self._extract_domain(url_or_domain)
        overlay = get_endpoint_overlay().lookup_validated(domain, url_or_domain)
        if overlay is not None:
            return AccessStrategy(
                source="overlay",
                method=overlay.method,
                domain=overlay.domain,
                tier=self._lookup_static(url_or_domain).tier,
                endpoint_url=overlay.endpoint_url,
                rewritten_url=overlay.rewritten_url,
                scope=overlay.scope,
                path_pattern=overlay.path_pattern,
                transform_kind=overlay.transform_kind,
                seed_urls=get_endpoint_overlay().get_validated_seed_urls(domain) if overlay.is_seed_only else [],
                method_hint=overlay.method,
            )

        info = self._lookup_static(url_or_domain)
        rewritten = ""
        seed_urls: List[str] = []
        if info.feed_prefix and "://" in (url_or_domain or ""):
            rewritten = info.feed_prefix + urlparse(url_or_domain).path
        elif info.feed_prefix:
            seed_urls = [info.feed_prefix]
        return AccessStrategy(
            source="static" if info.pattern != "*" else "default",
            method=info.method,
            domain=domain,
            tier=info.tier,
            endpoint_url=info.feed_prefix or info.official_api or info.json_api_hint or "",
            rewritten_url=rewritten,
            scope="domain",
            path_pattern="",
            transform_kind="",
            seed_urls=seed_urls,
            method_hint=info.method,
            response_time_ms=info.response_time_ms,
        )

    # True when resolved method is camoufox browser fetch.
    def needs_camoufox(self, url_or_domain: str) -> bool:
        return self.lookup(url_or_domain).method == "camoufox"

    # True when parsing_mode is nextjs_rsc for this domain.
    def prefers_nextjs_rsc(self, url_or_domain: str) -> bool:
        return self.lookup(url_or_domain).parsing_mode == "nextjs_rsc"

    # Group unique patterns by tier for operator reporting.
    def summary(self) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {
            "friendly": [],
            "moderate": [],
            "hardened": [],
            "fortress": [],
            "unknown": [],
        }
        seen: set[int] = set()
        for info in self._domains.values():
            marker = id(info)
            if marker in seen:
                continue
            seen.add(marker)
            tier = info.tier if info.tier in result else "unknown"
            result[tier].append(f"{info.pattern} [{info.method}] ({','.join(info.topics)})")
        return result

    # True when at least one domain pattern was loaded.
    @property
    def loaded(self) -> bool:
        return self._loaded


_registry: Optional[DomainRegistry] = None


# Shared DomainRegistry singleton.
def get_registry(config_path: Optional[str] = None) -> DomainRegistry:
    global _registry
    if _registry is None:
        _registry = DomainRegistry(config_path)
    return _registry


# Lazy proxy delegating attribute access to shared DomainRegistry singleton.
class _RegistryProxy:

    # Forward attribute lookup to get_registry() instance.
    def __getattr__(self, item):
        return getattr(get_registry(), item)


registry = _RegistryProxy()
