# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path

from .config import TRUST_PROFILES_DIR, TRUST_REGISTRY_PATH

HERE = Path(__file__).resolve().parent
ZIP_PATH = HERE / "majestic_million.zip"
CSV_NAME = "majestic_million.csv"
OUTPUT_PROFILE = TRUST_PROFILES_DIR / "majestic_web.json"

TIER_THRESHOLDS: list[tuple[int, str]] = [
    (50_000, "A"),
    (5_000, "B"),
    (500, "C"),
]


# Map RefSubNets count to trust tier A/B/C or None if below minimum.
def _tier_for(ref_subnets: int) -> str | None:
    for threshold, tier in TIER_THRESHOLDS:
        if ref_subnets >= threshold:
            return tier
    return None


# Open CSV text stream from majestic_million.zip.
def _extract_csv(zip_path: Path) -> io.TextIOWrapper:
    zf = zipfile.ZipFile(zip_path)
    names = zf.namelist()
    csv_name = next((n for n in names if n.endswith(".csv")), None)
    if csv_name is None:
        raise FileNotFoundError(f"No .csv file found inside {zip_path}. Contents: {names}")
    return io.TextIOWrapper(zf.open(csv_name), encoding="utf-8")


# Patterns already present in merged trust registry (profiles + monolith).
def _existing_patterns() -> set[str]:
    try:
        from core.registry.trust_registry import load_trust_registry

        _, _, domains = load_trust_registry()
        return set(domains.keys())
    except Exception:
        pass
    if TRUST_REGISTRY_PATH.is_file():
        try:
            data = json.loads(TRUST_REGISTRY_PATH.read_text(encoding="utf-8"))
            return {str(e.get("pattern", "")).lower() for e in data.get("domains", []) if e.get("pattern")}
        except Exception:
            pass
    return set()


# blocked_domain_contains fragments from merged trust blacklist.
def _blocked_fragments() -> list[str]:
    try:
        from core.registry.trust_registry import load_trust_registry

        _, blacklist, _ = load_trust_registry()
        return blacklist.get("blocked_domain_contains", [])
    except Exception:
        return []


# Domain entries already written to majestic_web.json profile.
def _load_existing_output() -> list[dict]:
    if OUTPUT_PROFILE.is_file():
        try:
            data = json.loads(OUTPUT_PROFILE.read_text(encoding="utf-8"))
            return [e for e in data.get("domains", []) if isinstance(e, dict) and "pattern" in e]
        except Exception:
            pass
    return []


# Import Majestic Million CSV into trust_registry_profiles/majestic_web.json.
def run(write: bool = False, stats: bool = False) -> None:
    if not ZIP_PATH.is_file():
        print(f"[skip] Majestic zip not found: {ZIP_PATH}")
        return

    print(f"Reading: {ZIP_PATH}")
    existing = _existing_patterns()
    blocked_fragments = _blocked_fragments()

    tier_counts: dict[str, int] = {
        "A": 0, "B": 0, "C": 0,
        "skip_low": 0, "skip_existing": 0, "skip_blocked": 0,
    }
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
    print(f"  Skipped (low authority):          {tier_counts['skip_low']:>7,}")
    print(f"  Skipped (already in registry):    {tier_counts['skip_existing']:>7,}")
    print(f"  Skipped (blacklisted):            {tier_counts['skip_blocked']:>7,}")
    print(f"  Total new entries: {total_new:,}")

    if not write:
        print("\n[dry-run] No changes written. Pass --write to apply.")
        return

    if total_new == 0:
        print("\n[skip] Nothing new to write.")
        return

    tier_order = {"A": 0, "B": 1, "C": 2}
    new_entries.sort(key=lambda e: (tier_order[e["tier"]], e["pattern"]))

    existing_output = _load_existing_output()
    existing_output_patterns = {str(e.get("pattern", "")).lower() for e in existing_output}
    truly_new = [e for e in new_entries if e["pattern"] not in existing_output_patterns]

    all_entries = existing_output + truly_new

    profile_data = {
        "profile": "majestic_web",
        "description": "Auto-imported from Majestic Million. Manual entries in other profiles override these.",
        "defaults": {"cat": "web"},
        "domains": all_entries,
    }

    OUTPUT_PROFILE.write_text(
        json.dumps(profile_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nWritten {len(truly_new):,} new entries ({len(all_entries):,} total) to {OUTPUT_PROFILE}")


# CLI entry for Majestic Million import dry-run or --write.
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import Majestic Million into trust_registry_profiles/majestic_web.json"
    )
    parser.add_argument("--write", action="store_true", help="Write output (default: dry-run)")
    parser.add_argument("--stats", action="store_true", help="Alias for dry-run")
    args = parser.parse_args()
    run(write=args.write and not args.stats, stats=args.stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
