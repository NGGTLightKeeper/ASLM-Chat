# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from core.registry.domain_registry import get_registry
from core.registry.trust_registry import get_trust_registry


NEUTRAL_CLASS = "general"


# One query class with normalized weight and optional reason string.
@dataclass(frozen=True)
class QueryClassWeight:
    name: str
    weight: float
    reason: str = ""


# Combined domain and trust routing multiplier with debug metadata.
@dataclass(frozen=True)
class RoutingScore:
    multiplier: float
    domain_multiplier: float
    trust_affinity: float
    trust_weight: float
    debug: dict = field(default_factory=dict)


# Normalize class weights to sum to 1; fallback to general on empty input.
def normalize_class_mix(classes: list[tuple[str, float, str]] | list[QueryClassWeight]) -> list[QueryClassWeight]:
    cleaned: list[QueryClassWeight] = []
    for item in classes:
        if isinstance(item, QueryClassWeight):
            name, weight, reason = item.name, item.weight, item.reason
        else:
            name, weight, reason = item
        name = str(name or "").strip()
        if not name:
            continue
        cleaned.append(QueryClassWeight(name=name, weight=max(0.0, float(weight)), reason=str(reason or "")))
    total = sum(item.weight for item in cleaned)
    if total <= 0:
        return [QueryClassWeight(NEUTRAL_CLASS, 1.0, "zero-mix-fallback")]
    return [
        QueryClassWeight(item.name, round(item.weight / total, 4), item.reason)
        for item in cleaned
        if item.weight > 0
    ]


# Ensure a general-class floor when a single non-general class dominates.
def ensure_general_fallback(classes: list[QueryClassWeight], *, floor: float = 0.18) -> list[QueryClassWeight]:
    if not classes:
        return [QueryClassWeight(NEUTRAL_CLASS, 1.0, "empty-fallback")]
    non_general = [item for item in classes if item.name != NEUTRAL_CLASS]
    has_general = any(item.name == NEUTRAL_CLASS for item in classes)
    if len(non_general) == 1 and not has_general:
        primary = non_general[0]
        return normalize_class_mix([
            primary,
            QueryClassWeight(NEUTRAL_CLASS, floor, f"secondary-fallback;primary={primary.name}"),
        ])
    return normalize_class_mix(classes)


# Convert class weight list to name → weight map.
def class_mix_map(classes: list[QueryClassWeight]) -> dict[str, float]:
    return {item.name: item.weight for item in classes}


# Distribute integer source budget across classes by normalized weights.
def allocate_source_budget(classes: list[QueryClassWeight], total: int) -> dict[str, int]:
    total = max(1, int(total))
    mix = ensure_general_fallback(normalize_class_mix(classes))
    raw = {item.name: item.weight * total for item in mix}
    allocation = {name: int(value) for name, value in raw.items()}
    for item in mix:
        if item.weight > 0 and allocation[item.name] <= 0:
            allocation[item.name] = 1
    remainder = total - sum(allocation.values())
    ordered = sorted(mix, key=lambda item: raw[item.name] - int(raw[item.name]), reverse=True)
    while remainder > 0:
        for item in ordered:
            allocation[item.name] += 1
            remainder -= 1
            if remainder <= 0:
                break
    while remainder < 0:
        for item in sorted(mix, key=lambda item: allocation[item.name], reverse=True):
            if allocation[item.name] > 1 or item.name == NEUTRAL_CLASS:
                allocation[item.name] -= 1
                remainder += 1
                if remainder >= 0:
                    break
    return allocation


# Weighted average over class mix; general uses default when absent from values.
def _weighted(values: dict[str, float], mix: dict[str, float], default: float = 1.0) -> float:
    if not mix:
        return default
    total = 0.0
    for name, weight in mix.items():
        if name == NEUTRAL_CLASS:
            total += weight * default
        else:
            total += weight * float(values.get(name, default))
    return total or default


# Lookup trust registry entry by URL host pattern.
def _trust_entry_for_url(trust_registry, url: str):
    host = urlparse(url or "").netloc.lower()
    for pattern, entry in getattr(trust_registry, "_lookup", {}).items():
        if host == pattern or host.endswith("." + pattern):
            return entry
    return None


# Compute combined domain and trust routing multiplier for one URL.
def compute_routing_score(url: str, classes: list[QueryClassWeight]) -> RoutingScore:
    mix = class_mix_map(ensure_general_fallback(normalize_class_mix(classes)))
    domain_registry = get_registry()
    trust_registry = get_trust_registry()
    info = domain_registry.lookup(url)
    strategy = domain_registry.resolve_access_strategy(url)

    # Path-prefix class weights (longest matching prefix wins).
    path = urlparse(url or "").path or "/"
    matched_path = ""
    path_weight = 1.0
    for candidate in sorted(info.path_weights, key=lambda item: len(item.path_prefix), reverse=True):
        if path.startswith(candidate.path_prefix):
            matched_path = candidate.path_prefix
            path_weight = _weighted(candidate.class_weights, mix)
            break

    base = float(info.base_weight or 1.0)
    class_weight = _weighted(info.class_weights, mix)
    demotion = _weighted(info.hard_demotions, mix)
    raw_domain = base * class_weight * demotion * path_weight
    domain_multiplier = max(0.55, min(1.45, raw_domain))

    # Trust tier affinity blended into final multiplier.
    entry = _trust_entry_for_url(trust_registry, url)
    if entry is not None:
        trust_affinity = max(0.55, min(1.25, _weighted(entry.class_affinity, mix)))
        trust_weight = float(trust_registry.get_weight(url) or 0.0)
        trust_pattern = entry.pattern
        trust_tier = entry.tier
    else:
        trust_affinity = 1.0
        trust_weight = 0.0
        trust_pattern = ""
        trust_tier = "?"

    multiplier = max(0.45, min(1.65, domain_multiplier * trust_affinity))
    return RoutingScore(
        multiplier=round(multiplier, 4),
        domain_multiplier=round(domain_multiplier, 4),
        trust_affinity=round(trust_affinity, 4),
        trust_weight=round(trust_weight, 4),
        debug={
            "class_mix": mix,
            "domain_pattern": info.pattern,
            "domain_tier": info.tier,
            "domain_method": info.method,
            "access_method": strategy.method,
            "access_source": strategy.source,
            "endpoint_url": strategy.endpoint_url,
            "base_weight": round(base, 4),
            "class_weight": round(class_weight, 4),
            "hard_demotion": round(demotion, 4),
            "path_prefix": matched_path,
            "path_weight": round(path_weight, 4),
            "trust_pattern": trust_pattern,
            "trust_tier": trust_tier,
        },
    )
