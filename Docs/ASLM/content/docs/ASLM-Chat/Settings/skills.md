---
title: "skills"
draft: false
---

## Module `skills`

`Settings/skills.py` — ASLM Chat Python module.

---

## Overview

Part of `Settings`. See **Related** for package index and callers.

---

## Classes

### `class SkillFile`

**Purpose:** Type `SkillFile` defined in `skills.py`.

---

## Public functions

#### `def ensure_skills_dir() -> Path`

**Purpose:** Ensure the project-level Skills root directory exists.

#### `def parse_front_matter(content) -> tuple[dict[str, Any], str]`

**Purpose:** Parse a small YAML-like front matter block from skill markdown.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def list_skills() -> dict[str, Any]`

**Purpose:** List all skill folders with metadata and file trees.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def create_skill_folder(name) -> dict[str, Any]`

**Purpose:** Create a new skill folder with a default SKILL.md template.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def rename_skill_folder(old_name, new_name) -> dict[str, Any]`

**Purpose:** Rename a skill folder and update its primary front matter name.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def delete_skill_folder(name) -> dict[str, Any]`

**Purpose:** Delete one skill folder and its contents.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def create_skill_subdirectory(folder, dir_path) -> dict[str, Any]`

**Purpose:** Create a subdirectory inside one skill folder.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def delete_skill_subdirectory(folder, dir_path) -> dict[str, Any]`

**Purpose:** Delete a subdirectory inside one skill folder.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def rename_skill_item(folder, old_path, new_path, kind) -> dict[str, Any]`

**Purpose:** Rename a file or directory inside one skill folder.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def read_skill_file(folder, file_path) -> dict[str, Any]`

**Purpose:** Read one skill file with parsed front matter metadata.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def write_skill_file(folder, file_path, content) -> dict[str, Any]`

**Purpose:** Write one skill file and return the updated skills listing.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def delete_skill_file(folder, file_path) -> dict[str, Any]`

**Purpose:** Delete one skill file and prune empty parent directories.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def parse_enabled_flag(value) -> bool`

**Purpose:** Parse a loose enabled flag from API or front matter input.

**Steps:**

1. Return the computed result to the caller.

#### `def set_skill_enabled(folder, enabled) -> dict[str, Any]`

**Purpose:** Toggle whether one skill is enabled and refresh sandbox sync when needed.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.

#### `def import_skill_files(skill_name, files) -> dict[str, Any]`

**Purpose:** Create a skill folder from browser-imported path/content pairs.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def clear_skill_config_refresh_pending() -> None`

**Purpose:** Clear any queued one-shot skills summary refresh (tests and tooling).

#### `def build_system_prompt_inventory() -> str`

**Purpose:** Build a system-prompt block listing enabled skills and their on-disk layout.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def build_system_prompt_skills_section(*, consume=…, include_baseline=…) -> str`

**Purpose:** Inject skills into the system prompt on the first turn or after enable toggles.

**Steps:**

1. Return the computed result to the caller.

#### `def build_system_prompt_skill_delta(*, consume=…, include_baseline=…) -> str`

**Purpose:** Backward-compatible alias for build_system_prompt_skills_section.

#### `def sync_skills_to_sandbox() -> dict[str, Any]`

**Purpose:** Mirror project Skills into the sandbox Skills directory.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

---

## Private functions

#### `def _is_hidden_part(part) -> bool`

**Purpose:** Return True when a path segment is hidden or reserved.

#### `def _validate_skill_name(name) -> str`

**Purpose:** Validate and return a safe skill folder name.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _normalize_relative_file_path(path) -> str`

**Purpose:** Normalize and validate a relative file path inside a skill folder.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _normalize_relative_dir_path(path) -> str`

**Purpose:** Normalize and validate a relative directory path inside a skill folder.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _skill_dir(name) -> Path`

**Purpose:** Resolve the on-disk directory for one skill name.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def _skill_file_path(folder, file_path) -> Path`

**Purpose:** Resolve an absolute path for one file inside a skill folder.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def _skill_subdir_path(folder, dir_path) -> Path`

**Purpose:** Resolve an absolute path for one subdirectory inside a skill folder.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def _safe_read_text(path) -> str`

**Purpose:** Read a text file with size and binary guards for the skills manager.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def _atomic_write_text(path, content) -> None`

**Purpose:** Write text atomically via a temporary file in the target directory.

#### `def _parse_scalar(value) -> Any`

**Purpose:** Parse one YAML-like front matter scalar value.

**Steps:**

1. Return the computed result to the caller.

#### `def _normalize_skill_source(meta) -> str`

**Purpose:** Normalize the skill source field from front matter metadata.

**Steps:**

1. Return the computed result to the caller.

#### `def _normalize_meta_for_storage(meta) -> dict[str, Any]`

**Purpose:** Strip legacy front matter keys before persisting metadata.

**Steps:**

1. Return the computed result to the caller.

#### `def _skill_created_at(stat) -> float`

**Purpose:** Return the best available creation timestamp for a skill folder.

**Steps:**

1. Return the computed result to the caller.

#### `def _format_front_matter(meta) -> str`

**Purpose:** Render front matter metadata as a markdown header block.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _primary_file_for_skill(skill_root) -> Path`

**Purpose:** Locate the primary markdown file for one skill folder.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _read_skill_meta(skill_root) -> tuple[dict[str, Any], str]`

**Purpose:** Read normalized metadata and the primary file path for one skill.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _file_node(path, root) -> SkillFile`

**Purpose:** Build one SkillFile node for the skills tree API.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_tree(path, root) -> list[dict[str, Any]]`

**Purpose:** Build the nested file tree for one skill folder.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _format_skill_tree_lines(nodes, *, indent=…) -> list[str]`

**Purpose:** Render enabled skill tree nodes as indented lines for the system prompt.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _pending_notify_path() -> Path`

**Purpose:** Return the path used to queue a one-shot skills config refresh.

#### `def _load_notify_state() -> dict[str, Any]`

**Purpose:** Load the pending skills notification state from disk.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _save_notify_state(state) -> None`

**Purpose:** Persist or clear the pending skills notification state.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def _migrate_legacy_notify_state() -> None`

**Purpose:** Migrate legacy notification files and re-queue refresh when needed.

#### `def _peek_config_refresh_pending() -> bool`

**Purpose:** Return whether a skills config refresh is pending without consuming it.

#### `def _consume_config_refresh_pending() -> bool`

**Purpose:** Return and clear the pending skills config refresh flag.

**Steps:**

1. Return the computed result to the caller.

#### `def _queue_skill_config_refresh() -> None`

**Purpose:** Queue a one-shot skills summary refresh for the next chat turn.

#### `def _sha256_file(path) -> str`

**Purpose:** Compute the SHA-256 digest of one file.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _enabled_skill_names(root) -> set[str]`

**Purpose:** List skill folder names that are currently enabled.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _iter_sync_files(root, skill_names) -> dict[str, dict[str, Any]]`

**Purpose:** Enumerate files under a skills root with size and hash metadata for sync.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _remove_tree_entry(path) -> None`

**Purpose:** Remove one file or directory during sandbox sync cleanup.

---

## Related

- [Settings/_index](../_index/)
