---
title: "doctor"
draft: false
---

## Module `doctor`

`Tools/mcp-web-search/core/registry/doctor.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\registry`. See **Related** for package index and callers.

---

## Classes

### `class DoctorReport`

**Purpose:** Type `DoctorReport` defined in `doctor.py`.

---

## Public functions

#### `def DoctorReport.error(msg) -> None`

**Purpose:** Append one error message.

#### `def DoctorReport.warn(msg) -> None`

**Purpose:** Append one warning message.

#### `def DoctorReport.info(msg) -> None`

**Purpose:** Append one info message.

#### `def DoctorReport.ok() -> bool`

**Purpose:** Implements `DoctorReport.ok` in `doctor.py`.

#### `def DoctorReport.print(*, verbose=…) -> None`

**Purpose:** Print errors, and optionally warnings and info, to stdout.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def check_domain_profiles(report) -> dict[str, list[str]]`

**Purpose:** Validate domain_profiles/ and return pattern → profile stems map.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def check_domain_monolith(report, profile_patterns) -> None`

**Purpose:** Report domain patterns present only in domain_registry.json monolith.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def check_trust_profiles(report) -> dict[str, list[str]]`

**Purpose:** Validate trust_registry_profiles/ and return pattern → profile stems map.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def check_trust_monolith(report, profile_patterns) -> None`

**Purpose:** Report trust patterns present only in trust_registry.json monolith.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def run_checks(*, strict_duplicates=…) -> DoctorReport`

**Purpose:** Run all domain and trust registry validation checks.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def main(argv) -> int`

**Purpose:** CLI entry: verify, report, or stats subcommands for registry validation.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _load_json(path) -> dict[str, Any] | None`

**Purpose:** Parse JSON file; return None on failure.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _iter_domains(data) -> list[dict[str, Any]]`

**Purpose:** Yield domain entries from profile data, skipping section headers.

#### `def _pattern(entry) -> str`

**Purpose:** Normalized pattern string from one domain entry.

#### `def _load_profile_patterns(profiles_dir, skip) -> dict[str, list[str]]`

**Purpose:** Collect pattern → profile stems from all profile JSON files.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [registry/_index](../../../../_index/)
