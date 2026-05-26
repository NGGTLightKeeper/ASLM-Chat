# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Import Majestic Million domains into trust_registry.json.

Usage:
    python core/registry/import_majestic.py [--dry-run] [--stats]

What it does:
    1. Extracts majestic_million.csv from majestic_million.zip (same directory)
    2. Maps domains to tiers by RefSubNets:
         A  — RefSubNets > 50 000  (global giants, major publishers)
         B  — RefSubNets >  5 000
         C  — RefSubNets >    500
       Below 500 → skipped (too low authority)
    3. Merges into trust_registry.json:
         - Manual entries (already in the file) always win
         - Blacklisted domains are never promoted
         - New domains are appended under cat "web"
"""

from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZIP_PATH = HERE / "majestic_million.zip"
CSV_NAME = "majestic_million.csv"
REGISTRY_PATH = HERE / "trust_registry.json"

# RefSubNets thresholds → tier
TIER_THRESHOLDS: list[tuple[int, str]] = [
    (50_000, "A"),
    (5_000,  "B"),
    (500,    "C"),
]


def _tier_for(ref_subnets: int) -> str | None:
    for threshold, tier in TIER_THRESHOLDS:
        if ref_subnets >= threshold:
            return tier
    return None


def _extract_csv(zip_path: Path) -> io.TextIOWrapper:
    zf = zipfile.ZipFile(zip_path)
    names = zf.namelist()
    csv_name = next((n for n in names if n.endswith(".csv")), None)
    if csv_name is None:
        raise FileNotFoundError(f"No .csv file found inside {zip_path}. Contents: {names}")
    return io.TextIOWrapper(zf.open(csv_name), encoding="utf-8")


def _load_registry(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _existing_patterns(registry: dict) -> set[str]:
    return {entry["pattern"] for entry in registry.get("domains", [])}


def _blocked_fragments(registry: dict) -> list[str]:
    legacy = registry.get("blacklist", {}).get("blocked_domain_contains", [])
    if legacy:
        return legacy
    try:
        from core.registry.trust_registry import load_trust_registry

        _, blacklist, _ = load_trust_registry()
        return blacklist.get("blocked_domain_contains", [])
    except Exception:
        return []


def run(dry_run: bool = False, stats: bool = False) -> None:
    print(f"Reading zip: {ZIP_PATH}")
    registry = _load_registry(REGISTRY_PATH)
    existing = _existing_patterns(registry)
    blocked_fragments = _blocked_fragments(registry)

    tier_counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "skip_low": 0, "skip_existing": 0, "skip_blocked": 0}
    new_entries: list[dict] = []

    csv_file = _extract_csv(ZIP_PATH)
    header = next(csv_file).strip().split(",")
    domain_idx = header.index("Domain")
    refsubnets_idx = header.index("RefSubNets")

    for raw_line in csv_file:
        parts = raw_line.strip().split(",")
        if len(parts) <= max(domain_idx, refsubnets_idx):
            continue
        domain = parts[domain_idx].strip().lower()
        try:
            ref_subnets = int(parts[refsubnets_idx].strip())
        except ValueError:
            continue

        tier = _tier_for(ref_subnets)
        if tier is None:
            tier_counts["skip_low"] += 1
            continue

        if domain in existing:
            tier_counts["skip_existing"] += 1
            continue

        if any(frag in domain for frag in blocked_fragments):
            tier_counts["skip_blocked"] += 1
            continue

        tier_counts[tier] += 1
        new_entries.append({"pattern": domain, "tier": tier, "cat": "web"})

    total_new = len(new_entries)
    print(f"\nResults:")
    print(f"  New A: {tier_counts['A']:>7,}")
    print(f"  New B: {tier_counts['B']:>7,}")
    print(f"  New C: {tier_counts['C']:>7,}")
    print(f"  Skipped (low authority): {tier_counts['skip_low']:>7,}")
    print(f"  Skipped (already in registry): {tier_counts['skip_existing']:>7,}")
    print(f"  Skipped (blacklisted): {tier_counts['skip_blocked']:>7,}")
    print(f"  Total new entries: {total_new:,}")

    if dry_run:
        print("\n[dry-run] No changes written.")
        return

    # Sort new entries: A first, then B, then C; alphabetically within tier
    tier_order = {"A": 0, "B": 1, "C": 2}
    new_entries.sort(key=lambda e: (tier_order[e["tier"]], e["pattern"]))

    registry["domains"].extend(new_entries)

    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=4)

    print(f"\nWritten {total_new:,} new entries to {REGISTRY_PATH}")
    print(f"Registry now has {len(registry['domains']):,} domain entries.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Majestic Million into trust_registry.json")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report without writing")
    parser.add_argument("--stats", action="store_true", help="(alias for --dry-run)")
    args = parser.parse_args()
    run(dry_run=args.dry_run or args.stats)
