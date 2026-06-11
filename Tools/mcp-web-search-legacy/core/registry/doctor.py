# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import (
    DOMAIN_PROFILES_DIR,
    DOMAIN_REGISTRY_PATH,
    TRUST_PROFILES_DIR,
    TRUST_REGISTRY_PATH,
)

_DOMAIN_VALID_TIERS = frozenset({"friendly", "moderate", "hardened", "fortress", "unknown"})
_DOMAIN_VALID_METHODS = frozenset({"http", "xml_feed", "json_api", "nodriver", "camoufox", "official_api", "skip"})
_TRUST_VALID_TIERS = frozenset({"A", "B", "C"})


# Aggregated validation errors, warnings, and info messages.
@dataclass
class DoctorReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)

    # Append one error message.
    def error(self, msg: str) -> None:
        self.errors.append(msg)

    # Append one warning message.
    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    # Append one info message.
    def info(self, msg: str) -> None:
        self.infos.append(msg)

    # True when no errors were recorded.
    @property
    def ok(self) -> bool:
        return not self.errors

    # Print errors, and optionally warnings and info, to stdout.
    def print(self, *, verbose: bool = True) -> None:
        if self.errors:
            print(f"\n{'='*60}")
            print(f"ERRORS ({len(self.errors)})")
            print(f"{'='*60}")
            for e in self.errors:
                print(f"  [ERROR] {e}")
        if self.warnings and verbose:
            print(f"\nWARNINGS ({len(self.warnings)})")
            for w in self.warnings:
                print(f"  [WARN]  {w}")
        if self.infos and verbose:
            print(f"\nINFO ({len(self.infos)})")
            for i in self.infos:
                print(f"  [INFO]  {i}")
        status = "PASS" if self.ok else "FAIL"
        print(f"\n{status}: {len(self.errors)} errors, {len(self.warnings)} warnings")


# Parse JSON file; return None on failure.
def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return None


# Yield domain entries from profile data, skipping section headers.
def _iter_domains(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in data.get("domains", []) if isinstance(e, dict) and "_section" not in e]


# Normalized pattern string from one domain entry.
def _pattern(entry: dict[str, Any]) -> str:
    return str(entry.get("pattern", "")).strip().lower()


# Collect pattern → profile stems from all profile JSON files.
def _load_profile_patterns(profiles_dir: Path, skip: frozenset[str]) -> dict[str, list[str]]:
    pattern_to_profiles: dict[str, list[str]] = defaultdict(list)
    for path in sorted(profiles_dir.glob("*.json")):
        if path.name.lower() in skip:
            continue
        data = _load_json(path)
        if not data:
            continue
        for entry in _iter_domains(data):
            p = _pattern(entry)
            if p:
                pattern_to_profiles[p].append(path.stem)
    return dict(pattern_to_profiles)


# Validate domain_profiles/ and return pattern → profile stems map.
def check_domain_profiles(report: DoctorReport) -> dict[str, list[str]]:
    profiles_dir = DOMAIN_PROFILES_DIR
    if not profiles_dir.is_dir():
        report.error(f"domain_profiles/ directory not found: {profiles_dir}")
        return {}

    skip = frozenset({"manifest.json"})
    pattern_to_profiles: dict[str, list[str]] = defaultdict(list)
    total_entries = 0

    for path in sorted(profiles_dir.glob("*.json")):
        if path.name.lower() in skip:
            continue
        data = _load_json(path)
        if data is None:
            report.error(f"domain_profiles/{path.name}: failed to parse JSON")
            continue
        for key in ("profile", "domains"):
            if key not in data:
                report.error(f"domain_profiles/{path.name}: missing required key '{key}'")

        seen_in_file: set[str] = set()
        for i, entry in enumerate(_iter_domains(data)):
            p = _pattern(entry)
            if not p:
                report.error(f"domain_profiles/{path.name}: entry[{i}] missing 'pattern'")
                continue
            total_entries += 1

            tier = str(entry.get("tier", "unknown")).lower()
            if tier not in _DOMAIN_VALID_TIERS:
                report.error(
                    f"domain_profiles/{path.name}: pattern='{p}' invalid tier '{tier}'"
                    f" (valid: {sorted(_DOMAIN_VALID_TIERS)})"
                )
            method = str(entry.get("method", "http")).lower()
            if method not in _DOMAIN_VALID_METHODS:
                report.error(
                    f"domain_profiles/{path.name}: pattern='{p}' invalid method '{method}'"
                    f" (valid: {sorted(_DOMAIN_VALID_METHODS)})"
                )

            for num_field in ("rps", "base_weight"):
                val = entry.get(num_field)
                if val is not None:
                    try:
                        f = float(val)
                        if not (0.0 <= f <= 1000.0):
                            report.warn(
                                f"domain_profiles/{path.name}: pattern='{p}' {num_field}={f} out of range [0,1000]"
                            )
                    except (TypeError, ValueError):
                        report.error(
                            f"domain_profiles/{path.name}: pattern='{p}' {num_field} not a number"
                        )

            if p in seen_in_file:
                report.error(
                    f"domain_profiles/{path.name}: duplicate pattern '{p}' within same file"
                )
            seen_in_file.add(p)
            pattern_to_profiles[p].append(path.stem)

    cross_dups = {p: profiles for p, profiles in pattern_to_profiles.items() if len(profiles) > 1}
    if cross_dups:
        report.warn(
            f"domain_profiles: {len(cross_dups)} cross-profile duplicate pattern(s) "
            f"(merge-order-dependent): {', '.join(sorted(cross_dups)[:10])}"
            + (" ..." if len(cross_dups) > 10 else "")
        )

    report.info(f"domain_profiles: {total_entries} entries across {len(pattern_to_profiles)} unique patterns")
    return dict(pattern_to_profiles)


# Report domain patterns present only in domain_registry.json monolith.
def check_domain_monolith(report: DoctorReport, profile_patterns: dict[str, list[str]]) -> None:
    if not DOMAIN_REGISTRY_PATH.is_file():
        report.info("domain_registry.json not found (already removed or not present)")
        return

    data = _load_json(DOMAIN_REGISTRY_PATH)
    if data is None:
        report.error(f"domain_registry.json: failed to parse JSON")
        return

    monolith_patterns = {_pattern(e) for e in _iter_domains(data) if _pattern(e)}
    monolith_only = monolith_patterns - set(profile_patterns)
    profile_only = set(profile_patterns) - monolith_patterns

    report.info(
        f"domain_registry.json: {len(monolith_patterns)} patterns; "
        f"{len(monolith_only)} monolith-only; {len(profile_only)} profile-only"
    )
    if monolith_only:
        report.warn(
            f"domain monolith-only patterns ({len(monolith_only)}): "
            + ", ".join(sorted(monolith_only)[:15])
            + (" ..." if len(monolith_only) > 15 else "")
        )


# Validate trust_registry_profiles/ and return pattern → profile stems map.
def check_trust_profiles(report: DoctorReport) -> dict[str, list[str]]:
    profiles_dir = TRUST_PROFILES_DIR
    if not profiles_dir.is_dir():
        report.error(f"trust_registry_profiles/ directory not found: {profiles_dir}")
        return {}

    global_path = profiles_dir / "_global.json"
    if not global_path.is_file():
        report.warn("trust_registry_profiles/_global.json not found (tiers and blacklist will come from monolith)")
    else:
        gdata = _load_json(global_path)
        if gdata is None:
            report.error("trust_registry_profiles/_global.json: failed to parse JSON")
        else:
            if "tiers" not in gdata:
                report.warn("trust_registry_profiles/_global.json: missing 'tiers'")
            if "blacklist" not in gdata:
                report.warn("trust_registry_profiles/_global.json: missing 'blacklist'")

    skip = frozenset({"manifest.json", "_global.json"})
    pattern_to_profiles: dict[str, list[str]] = defaultdict(list)
    total_entries = 0

    for path in sorted(profiles_dir.glob("*.json")):
        if path.name.lower() in skip:
            continue
        data = _load_json(path)
        if data is None:
            report.error(f"trust_registry_profiles/{path.name}: failed to parse JSON")
            continue
        for key in ("profile", "domains"):
            if key not in data:
                report.error(f"trust_registry_profiles/{path.name}: missing required key '{key}'")

        seen_in_file: set[str] = set()
        for i, entry in enumerate(_iter_domains(data)):
            p = _pattern(entry)
            if not p:
                report.error(f"trust_registry_profiles/{path.name}: entry[{i}] missing 'pattern'")
                continue
            total_entries += 1

            tier = str(entry.get("tier", "C")).upper()
            if tier not in _TRUST_VALID_TIERS:
                report.error(
                    f"trust_registry_profiles/{path.name}: pattern='{p}' invalid tier '{tier}'"
                    f" (valid: {sorted(_TRUST_VALID_TIERS)})"
                )

            affinity = entry.get("class_affinity") or {}
            if isinstance(affinity, dict):
                for cls, val in affinity.items():
                    try:
                        f = float(val)
                        if not (0.0 <= f <= 1.5):
                            report.warn(
                                f"trust_registry_profiles/{path.name}: pattern='{p}' "
                                f"class_affinity['{cls}']={f} out of range [0.0, 1.5]"
                            )
                    except (TypeError, ValueError):
                        report.error(
                            f"trust_registry_profiles/{path.name}: pattern='{p}' "
                            f"class_affinity['{cls}'] not a number"
                        )

            if p in seen_in_file:
                report.error(
                    f"trust_registry_profiles/{path.name}: duplicate pattern '{p}' within same file"
                )
            seen_in_file.add(p)
            pattern_to_profiles[p].append(path.stem)

    cross_dups = {p: profiles for p, profiles in pattern_to_profiles.items() if len(profiles) > 1}
    if cross_dups:
        report.warn(
            f"trust_registry_profiles: {len(cross_dups)} cross-profile duplicate(s): "
            f"{', '.join(sorted(cross_dups)[:10])}"
            + (" ..." if len(cross_dups) > 10 else "")
        )

    report.info(f"trust_registry_profiles: {total_entries} entries across {len(pattern_to_profiles)} unique patterns")
    return dict(pattern_to_profiles)


# Report trust patterns present only in trust_registry.json monolith.
def check_trust_monolith(report: DoctorReport, profile_patterns: dict[str, list[str]]) -> None:
    if not TRUST_REGISTRY_PATH.is_file():
        report.info("trust_registry.json not found (already removed or not present)")
        return

    data = _load_json(TRUST_REGISTRY_PATH)
    if data is None:
        report.error("trust_registry.json: failed to parse JSON")
        return

    monolith_patterns = {_pattern(e) for e in _iter_domains(data) if _pattern(e)}
    monolith_only = monolith_patterns - set(profile_patterns)
    profile_only = set(profile_patterns) - monolith_patterns

    report.info(
        f"trust_registry.json: {len(monolith_patterns)} patterns; "
        f"{len(monolith_only)} monolith-only; {len(profile_only)} profile-only"
    )
    if monolith_only:
        report.warn(
            f"trust monolith-only patterns ({len(monolith_only)}): "
            + ", ".join(sorted(monolith_only)[:20])
            + (" ..." if len(monolith_only) > 20 else "")
        )


# Run all domain and trust registry validation checks.
def run_checks(*, strict_duplicates: bool = False) -> DoctorReport:
    report = DoctorReport()

    domain_profiles = check_domain_profiles(report)
    check_domain_monolith(report, domain_profiles)

    trust_profiles = check_trust_profiles(report)
    check_trust_monolith(report, trust_profiles)

    if strict_duplicates:
        cross_dup_warns = [w for w in report.warnings if "cross-profile duplicate" in w]
        for w in cross_dup_warns:
            report.warnings.remove(w)
            report.errors.append(w.replace("[WARN]", "[ERROR]"))

    return report


# CLI entry: verify, report, or stats subcommands for registry validation.
def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate domain and trust registry data",
        prog="python -m core.registry.doctor",
    )
    sub = parser.add_subparsers(dest="cmd")

    verify_p = sub.add_parser("verify", help="Exit 0 on pass, 1 on any error")
    verify_p.add_argument("--strict-duplicates", action="store_true",
                          help="Treat cross-profile duplicates as errors")
    verify_p.add_argument("--quiet", action="store_true",
                          help="Only print errors, suppress warnings and info")

    report_p = sub.add_parser("report", help="Print full report, always exit 0")
    report_p.add_argument("--strict-duplicates", action="store_true")

    sub.add_parser("stats", help="Print counts only, always exit 0")

    args = parser.parse_args(argv)
    cmd = args.cmd or "report"

    strict = getattr(args, "strict_duplicates", False)
    quiet = getattr(args, "quiet", False)

    report = run_checks(strict_duplicates=strict)

    if cmd == "stats":
        for i in report.infos:
            print(i)
        return 0

    report.print(verbose=not quiet)

    if cmd == "verify":
        return 0 if report.ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
