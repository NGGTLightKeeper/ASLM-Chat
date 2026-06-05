---
title: "tests"
draft: false
---

## Module `tests`

`Apps/Data/tests.py` — ASLM Chat Python module.

---

## Overview

Part of `Apps\Data`. See **Related** for package index and callers.

---

## Classes

### `class ToolRegistryTestCase`

**Purpose:** Provide helpers for exercising local ``Tools/*/mcp-server.py`` discovery.

### `class ChatMessageModelTests`

**Purpose:** Verify string helpers on persisted chat data.

### `class MessageImageTests`

**Purpose:** Verify helper serialization on stored message images.

### `class MessageAttachmentTests`

**Purpose:** Verify helper behavior for normalized message attachments.

### `class OllamaPresetTests`

**Purpose:** Verify per-model Ollama preset lifecycle helpers.

### `class LmsPresetTests`

**Purpose:** Verify per-model LM Studio preset lifecycle helpers.

### `class LocalServerRegistryTests`

**Purpose:** Verify discovery and execution of local MCP-style server modules.

---

## Test methods

#### `def ToolRegistryTestCase.setUp()`

**Purpose:** Create an isolated tools directory.

#### `def ToolRegistryTestCase.tearDown()`

**Purpose:** Restore the original registry state.

#### `def ToolRegistryTestCase.write_server(folder, body) -> None`

**Purpose:** Write a temporary MCP server module.

#### `def ChatMessageModelTests.test_chat_and_message_string_representations_are_readable()`

**Purpose:** Test chat and message string values stay readable.

**Steps:**

1. Read or write Django ORM records.

#### `def MessageImageTests.test_data_url_builds_valid_prefix()`

**Purpose:** Ensure data URLs include the expected prefix.

**Steps:**

1. Read or write Django ORM records.

#### `def MessageAttachmentTests.setUp()`

**Purpose:** Set up a message for attachment records.

**Steps:**

1. Read or write Django ORM records.

#### `def MessageAttachmentTests.test_data_url_and_image_detection_use_stored_metadata()`

**Purpose:** Ensure data URLs and image detection use stored metadata.

**Steps:**

1. Read or write Django ORM records.

#### `def MessageAttachmentTests.test_attachment_ordering_uses_order_then_id()`

**Purpose:** Ensure attachment query ordering is stable for the UI.

**Steps:**

1. Iterate and transform or accumulate state.
2. Read or write Django ORM records.

#### `def OllamaPresetTests.test_ensure_state_creates_default_preset()`

**Purpose:** Create the default preset when no saved state exists.

#### `def OllamaPresetTests.test_ensure_state_promotes_default_when_no_active_preset_exists()`

**Purpose:** Promote the default preset when saved state has no active preset.

**Steps:**

1. Iterate and transform or accumulate state.
2. Read or write Django ORM records.

#### `def OllamaPresetTests.test_ensure_state_keeps_only_one_active_preset()`

**Purpose:** Deactivate duplicate active presets to keep runtime state deterministic.

**Steps:**

1. Iterate and transform or accumulate state.
2. Read or write Django ORM records.

#### `def OllamaPresetTests.test_sync_from_default_creates_custom_active_preset()`

**Purpose:** Clone the default preset when the active config changes.

**Steps:**

1. Read or write Django ORM records.

#### `def OllamaPresetTests.test_sync_unchanged_default_config_does_not_create_custom_preset()`

**Purpose:** Keep the default preset active when the config has not changed.

**Steps:**

1. Read or write Django ORM records.

#### `def OllamaPresetTests.test_sync_custom_active_preset_updates_in_place()`

**Purpose:** Update custom active presets in place.

**Steps:**

1. Read or write Django ORM records.

#### `def OllamaPresetTests.test_delete_active_custom_preset_falls_back_to_default()`

**Purpose:** Fall back to the default preset after deleting the active custom one.

**Steps:**

1. Read or write Django ORM records.

#### `def OllamaPresetTests.test_activate_preset_switches_active_record()`

**Purpose:** Select a custom preset and deactivate the previous active one.

**Steps:**

1. Read or write Django ORM records.

#### `def OllamaPresetTests.test_default_preset_cannot_be_renamed_or_deleted()`

**Purpose:** Reject unsafe operations against the default preset.

#### `def OllamaPresetTests.test_sync_drops_unsupported_runtime_keys_from_preset_config()`

**Purpose:** Drop unsupported runtime keys before saving a preset.

**Steps:**

1. Read or write Django ORM records.

#### `def OllamaPresetTests.test_normalize_config_removes_empty_and_unsupported_values()`

**Purpose:** Normalize compact configs and keep only supported runtime keys.

#### `def LmsPresetTests.test_ensure_state_creates_default_preset(mock_get_model_settings)`

**Purpose:** Implements `LmsPresetTests.test_ensure_state_creates_default_preset` in `tests.py`.

#### `def LmsPresetTests.test_ensure_state_promotes_default_when_no_active_preset_exists(mock_get_model_settings)`

**Purpose:** Implements `LmsPresetTests.test_ensure_state_promotes_default_when_no_active_preset_exists` in `tests.py`.

**Steps:**

1. Iterate and transform or accumulate state.
2. Read or write Django ORM records.

#### `def LmsPresetTests.test_sync_from_default_creates_custom_active_preset(mock_get_model_settings)`

**Purpose:** Implements `LmsPresetTests.test_sync_from_default_creates_custom_active_preset` in `tests.py`.

**Steps:**

1. Read or write Django ORM records.

#### `def LmsPresetTests.test_sync_unchanged_default_config_does_not_create_custom_preset(mock_get_model_settings)`

**Purpose:** Implements `LmsPresetTests.test_sync_unchanged_default_config_does_not_create_custom_preset` in `tests.py`.

**Steps:**

1. Read or write Django ORM records.

#### `def LmsPresetTests.test_sync_custom_active_preset_updates_in_place(mock_get_model_settings)`

**Purpose:** Implements `LmsPresetTests.test_sync_custom_active_preset_updates_in_place` in `tests.py`.

**Steps:**

1. Read or write Django ORM records.

#### `def LmsPresetTests.test_delete_active_custom_preset_falls_back_to_default(mock_get_model_settings)`

**Purpose:** Implements `LmsPresetTests.test_delete_active_custom_preset_falls_back_to_default` in `tests.py`.

**Steps:**

1. Read or write Django ORM records.

#### `def LmsPresetTests.test_activate_preset_switches_active_record(mock_get_model_settings)`

**Purpose:** Implements `LmsPresetTests.test_activate_preset_switches_active_record` in `tests.py`.

**Steps:**

1. Read or write Django ORM records.

#### `def LmsPresetTests.test_default_preset_cannot_be_renamed_or_deleted(mock_get_model_settings)`

**Purpose:** Implements `LmsPresetTests.test_default_preset_cannot_be_renamed_or_deleted` in `tests.py`.

#### `def LmsPresetTests.test_normalize_config_moves_top_level_options_into_operation()`

**Purpose:** Normalize legacy top-level options into the operation block.

#### `def LocalServerRegistryTests.test_list_servers_discovers_valid_server_modules()`

**Purpose:** Discover valid local server modules.

**Steps:**

1. Return the computed result to the caller.

#### `def LocalServerRegistryTests.test_supports_filter_hides_servers_for_unsupported_engines()`

**Purpose:** Hide servers that do not support the requested engine.

**Steps:**

1. Return the computed result to the caller.

#### `def LocalServerRegistryTests.test_build_ollama_tools_registers_multiple_tools()`

**Purpose:** Build one OpenAI-style tool entry per local server tool.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def LocalServerRegistryTests.test_call_ollama_tool_serializes_results_and_passes_context()`

**Purpose:** Pass context through tool execution and serialize the result.

**Steps:**

1. Return the computed result to the caller.

#### `def LocalServerRegistryTests.test_invalid_server_modules_are_skipped()`

**Purpose:** Skip invalid local server modules without breaking discovery.

#### `def LocalServerRegistryTests.test_tool_handlers_are_supported_without_generic_dispatcher()`

**Purpose:** Execute servers that expose dedicated tool handlers.

**Steps:**

1. Return the computed result to the caller.

#### `def LocalServerRegistryTests.test_async_tool_handlers_are_supported()`

**Purpose:** Execute async tool handlers through the sync registry API.

**Steps:**

1. Return the computed result to the caller.

#### `def LocalServerRegistryTests.test_external_worker_session_skips_heartbeat_lines()`

**Purpose:** Test persistent workers ignore heartbeat lines and wait for the final envelope.

#### `def LocalServerRegistryTests.test_external_worker_session_times_out_silent_worker()`

**Purpose:** Test a silent persistent worker is killed instead of blocking forever.

**Steps:**

1. Return the computed result to the caller.

#### `def LocalServerRegistryTests.test_call_ollama_tool_returns_error_for_unknown_alias()`

**Purpose:** Return a readable error for unknown tool aliases.

---

## Related

- [Data/_index](../../_index/)
