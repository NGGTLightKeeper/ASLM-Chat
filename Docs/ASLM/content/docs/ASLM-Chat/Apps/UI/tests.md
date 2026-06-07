---
title: "tests"
draft: false
---

## Module `tests`

`Apps/UI/tests.py` — ASLM Chat Python module.

---

## Overview

Part of `Apps\UI`. See **Related** for package index and callers.

---

## Classes

### `class FakeGoogleError`

**Purpose:** Type `FakeGoogleError` defined in `tests.py`.

### `class ToolRegistryTestMixin`

**Purpose:** Type `ToolRegistryTestMixin` defined in `tests.py`.

### `class SkillsApiTests`

**Purpose:** Type `SkillsApiTests` defined in `tests.py`.

### `class SkillsModelContextTests`

**Purpose:** Type `SkillsModelContextTests` defined in `tests.py`.

### `class SkillsSandboxDispatchTests`

**Purpose:** Type `SkillsSandboxDispatchTests` defined in `tests.py`.

### `class ToolQuotaTests`

**Purpose:** Type `ToolQuotaTests` defined in `tests.py`.

### `class ModelNameExtractionTests`

**Purpose:** Type `ModelNameExtractionTests` defined in `tests.py`.

### `class AttachmentNormalizationTests`

**Purpose:** Type `AttachmentNormalizationTests` defined in `tests.py`.

### `class AttachmentExtractionTests`

**Purpose:** Type `AttachmentExtractionTests` defined in `tests.py`.

### `class UploadedFileManifestTests`

**Purpose:** Type `UploadedFileManifestTests` defined in `tests.py`.

### `class UploadFilesApiTests`

**Purpose:** Type `UploadFilesApiTests` defined in `tests.py`.

### `class UploadRoutingTests`

**Purpose:** Type `UploadRoutingTests` defined in `tests.py`.

### `class StaticCacheVersionTests`

**Purpose:** Type `StaticCacheVersionTests` defined in `tests.py`.

### `class MainViewTests`

**Purpose:** Type `MainViewTests` defined in `tests.py`.

### `class OllamaOptionMappingTests`

**Purpose:** Type `OllamaOptionMappingTests` defined in `tests.py`.

### `class OllamaModelInfoTests`

**Purpose:** Type `OllamaModelInfoTests` defined in `tests.py`.

### `class OpenAiOptionMappingTests`

**Purpose:** Type `OpenAiOptionMappingTests` defined in `tests.py`.

### `class OpenAiAdapterTests`

**Purpose:** Type `OpenAiAdapterTests` defined in `tests.py`.

### `class GoogleGenAiAdapterTests`

**Purpose:** Type `GoogleGenAiAdapterTests` defined in `tests.py`.

### `class EngineRegistryTests`

**Purpose:** Type `EngineRegistryTests` defined in `tests.py`.

### `class EngineAvailabilitySettingsTests`

**Purpose:** Type `EngineAvailabilitySettingsTests` defined in `tests.py`.

### `class LmsAdapterTests`

**Purpose:** Type `LmsAdapterTests` defined in `tests.py`.

### `class ViewFormattingTests`

**Purpose:** Type `ViewFormattingTests` defined in `tests.py`.

### `class BrowserPortalApiTests`

**Purpose:** Type `BrowserPortalApiTests` defined in `tests.py`.

### `class ModelInfoCacheTests`

**Purpose:** Type `ModelInfoCacheTests` defined in `tests.py`.

### `class ContextCompressionBudgetTests`

**Purpose:** Type `ContextCompressionBudgetTests` defined in `tests.py`.

### `class ChatApiTests`

**Purpose:** Type `ChatApiTests` defined in `tests.py`.

### `class RuntimeSettingsApiTests`

**Purpose:** Type `RuntimeSettingsApiTests` defined in `tests.py`.

### `class ToolApiTests`

**Purpose:** Type `ToolApiTests` defined in `tests.py`.

### `class OllamaPresetApiTests`

**Purpose:** Type `OllamaPresetApiTests` defined in `tests.py`.

### `class LmsPresetApiTests`

**Purpose:** Type `LmsPresetApiTests` defined in `tests.py`.

### `class MessageIdAndRegenerateTests`

**Purpose:** Type `MessageIdAndRegenerateTests` defined in `tests.py`.

---

## Test methods

#### `def FakeGoogleError.__init__(code, status, message, *, details=…) -> None`

**Purpose:** Implements `FakeGoogleError.__init__` in `tests.py`.

#### `def ToolRegistryTestMixin.setUp()`

**Purpose:** Create an isolated tools directory.

#### `def ToolRegistryTestMixin.tearDown()`

**Purpose:** Restore the original registry state.

#### `def ToolRegistryTestMixin.write_server(folder, body) -> None`

**Purpose:** Write a temporary MCP server.

#### `def SkillsApiTests.setUp()`

**Purpose:** Prepare shared fixtures for each test case.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def SkillsApiTests.tearDown()`

**Purpose:** Clean up fixtures created for each test case.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def SkillsApiTests.test_skills_root_created_and_crud_validates_paths()`

**Purpose:** Verify skills root created and crud validates paths.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def SkillsApiTests.test_front_matter_summary_and_prompt_inventory()`

**Purpose:** Verify front matter summary and prompt inventory.

#### `def SkillsApiTests.test_disable_skill_queues_refreshed_inventory_for_next_prompt()`

**Purpose:** Verify disable skill queues refreshed inventory for next prompt.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def SkillsApiTests.test_sync_mirrors_skills_and_overrides_sandbox()`

**Purpose:** Verify sync mirrors skills and overrides sandbox.

#### `def SkillsApiTests.test_sync_excludes_disabled_skills_from_sandbox()`

**Purpose:** Verify sync excludes disabled skills from sandbox.

#### `def SkillsApiTests.test_disable_skill_removes_folder_from_sandbox()`

**Purpose:** Verify disable skill removes folder from sandbox.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def SkillsApiTests.test_create_skill_subdirectory()`

**Purpose:** Verify create skill subdirectory.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def SkillsApiTests.test_create_skill_subdirectory_rejects_duplicate()`

**Purpose:** Verify create skill subdirectory rejects duplicate.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def SkillsApiTests.test_create_skill_subdirectory_rejects_traversal()`

**Purpose:** Verify create skill subdirectory rejects traversal.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def SkillsApiTests.test_create_skill_subdirectory_rejects_file_extension()`

**Purpose:** Verify create skill subdirectory rejects file extension.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def SkillsApiTests.test_rename_and_delete_skill_subdirectory()`

**Purpose:** Verify rename and delete skill subdirectory.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def SkillsApiTests.test_rename_skill_file()`

**Purpose:** Verify rename skill file.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def SkillsApiTests.test_import_skill_creates_folder_and_files()`

**Purpose:** Verify import skill creates folder and files.

**Steps:**

1. Iterate and transform or accumulate state.
2. Parse or serialize JSON payloads.

#### `def SkillsApiTests.test_import_skill_merges_into_existing_folder()`

**Purpose:** Verify import skill merges into existing folder.

**Steps:**

1. Iterate and transform or accumulate state.
2. Parse or serialize JSON payloads.

#### `def SkillsModelContextTests.setUp()`

**Purpose:** Prepare shared fixtures for each test case.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def SkillsModelContextTests.tearDown()`

**Purpose:** Clean up fixtures created for each test case.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def SkillsModelContextTests.test_enabled_skills_appear_only_on_first_chat_turn()`

**Purpose:** Verify enabled skills appear only on first chat turn.

#### `def SkillsModelContextTests.test_chat_api_first_turn_includes_skills_baseline()`

**Purpose:** Verify chat api first turn includes skills baseline.

**Steps:**

1. Read or write Django ORM records.

#### `def SkillsModelContextTests.test_static_disabled_skill_is_omitted_from_inventory()`

**Purpose:** Verify static disabled skill is omitted from inventory.

#### `def SkillsModelContextTests.test_disable_sends_updated_inventory_once()`

**Purpose:** Verify disable sends updated inventory once.

#### `def SkillsModelContextTests.test_context_usage_style_compose_does_not_consume_pending_refresh()`

**Purpose:** Verify context usage style compose does not consume pending refresh.

#### `def SkillsModelContextTests.test_enable_queues_refreshed_inventory_with_enabled_skill()`

**Purpose:** Verify enable queues refreshed inventory with enabled skill.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def SkillsModelContextTests.test_re_toggle_without_change_does_not_queue_refresh()`

**Purpose:** Verify re toggle without change does not queue refresh.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def SkillsModelContextTests.test_toggle_still_queues_inventory_when_sandbox_sync_fails(_sync_mock)`

**Purpose:** Verify toggle still queues inventory when sandbox sync fails.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def SkillsSandboxDispatchTests.test_sandbox_tool_dispatch_syncs_skills_first()`

**Purpose:** Verify sandbox tool dispatch syncs skills first.

#### `def ToolQuotaTests.test_high_effort_web_search_limits_to_three_calls()`

**Purpose:** High-effort web search is expensive, so keep it bounded per response.

#### `def ToolQuotaTests.test_normal_web_search_keeps_default_quota()`

**Purpose:** Lower-effort searches keep the existing broader budget.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def ModelNameExtractionTests.test_extracts_name_from_string()`

**Purpose:** Test extracts name from string.

#### `def ModelNameExtractionTests.test_extracts_name_from_mapping()`

**Purpose:** Test extracts name from mapping.

#### `def ModelNameExtractionTests.test_prefers_id_over_friendly_name()`

**Purpose:** Test prefers id over friendly name.

#### `def AttachmentNormalizationTests.test_invalid_base64_attachments_are_ignored()`

**Purpose:** Test invalid base64 attachments are ignored before persistence.

#### `def AttachmentNormalizationTests.test_data_url_attachments_are_normalized_for_storage()`

**Purpose:** Test data URL attachments keep MIME, filename and decoded size.

#### `def AttachmentNormalizationTests.test_legacy_image_payloads_are_normalized_with_detected_mime()`

**Purpose:** Test legacy image payloads are detected and named.

#### `def AttachmentNormalizationTests.test_attachment_order_uses_surviving_items_only()`

**Purpose:** Test empty entries are skipped without breaking later order values.

#### `def AttachmentExtractionTests.test_text_attachment_extraction_is_cached_on_record()`

**Purpose:** Cache extracted text back onto the attachment record.

**Steps:**

1. Read or write Django ORM records.

#### `def AttachmentExtractionTests.test_cached_attachment_text_is_reused()`

**Purpose:** Reuse cached text without trying to decode a broken payload.

**Steps:**

1. Read or write Django ORM records.

#### `def UploadedFileManifestTests.test_text_manifest_uses_bounded_preview()`

**Purpose:** Test text files expose bounded previews instead of unbounded content.

#### `def UploadedFileManifestTests.test_binary_manifest_does_not_expose_text_preview()`

**Purpose:** Test binary-looking files do not get decoded through permissive encodings.

#### `def UploadedFileManifestTests.test_upload_name_is_normalized_to_basename()`

**Purpose:** Test uploaded names are reduced to safe basenames.

#### `def UploadedFileManifestTests.test_zip_manifest_includes_archive_tree()`

**Purpose:** Test zip files include a bounded archive tree without unpacking.

#### `def UploadedFileManifestTests.test_pdf_manifest_extracts_text_layer()`

**Purpose:** Test PDF files with a text layer expose a model-readable preview.

#### `def UploadedFileManifestTests.test_docx_manifest_extracts_document_xml_text()`

**Purpose:** Test docx files expose text from their document XML.

#### `def UploadedFileManifestTests.test_pptx_manifest_extracts_slide_text()`

**Purpose:** Test pptx files expose slide text from their slide XML.

#### `def UploadedFileManifestTests.test_xlsx_manifest_extracts_sheet_text()`

**Purpose:** Test xlsx files expose a small table preview from worksheet XML.

#### `def UploadedFileManifestTests.test_non_vision_image_manifest_keeps_sandbox_without_text()`

**Purpose:** Test non-vision image uploads keep metadata and sandbox access only.

#### `def UploadFilesApiTests.setUp()`

**Purpose:** Isolate sandbox writes in a temporary directory.

#### `def UploadFilesApiTests.tearDown()`

**Purpose:** Clean up the temporary sandbox.

#### `def UploadFilesApiTests.test_upload_api_returns_public_file_card_payload_only()`

**Purpose:** Test the upload API returns only card-safe fields while storing a private manifest.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def UploadFilesApiTests.test_upload_api_labels_zip_archive_for_card()`

**Purpose:** Test archive uploads get a simple English card label.

#### `def UploadFilesApiTests.test_upload_api_accepts_unknown_extension_as_generic_file()`

**Purpose:** Test unusual extensions are accepted and routed as generic files.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def UploadFilesApiTests.test_upload_limit_is_16_gb()`

**Purpose:** Test the configured upload ceiling matches the advertised large-video contract.

#### `def UploadFilesApiTests.test_upload_api_uses_lightweight_manifest_after_inline_threshold()`

**Purpose:** Test uploads beyond the inline manifest threshold are stored without full in-memory extraction.

**Steps:**

1. Iterate and transform or accumulate state.
2. Parse or serialize JSON payloads.

#### `def UploadFilesApiTests.test_upload_api_reports_oversized_files()`

**Purpose:** Test oversize uploads are rejected before being stored.

#### `def UploadFilesApiTests.test_uploaded_file_content_supports_suffix_byte_range()`

**Purpose:** Test media content endpoint supports suffix ranges needed by MP4 metadata reads.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def UploadFilesApiTests.test_uploaded_file_content_chunks_open_ended_range()`

**Purpose:** Test open-ended media ranges are chunked so playback can start without reading the rest of a large file.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def UploadFilesApiTests.test_shared_file_download_supports_byte_range()`

**Purpose:** Test model-shared files use the same range streaming path as uploaded files.

#### `def UploadFilesApiTests.test_shared_file_download_rejects_project_absolute_path()`

**Purpose:** Test shared-file downloads are limited to the sandbox workspace.

#### `def UploadFilesApiTests.test_shared_file_download_allows_container_sandbox_path()`

**Purpose:** Test container-style sandbox paths are still mapped to the host sandbox.

#### `def UploadFilesApiTests.test_upload_api_requires_files()`

**Purpose:** Test empty upload requests fail before returning a card payload.

#### `def UploadFilesApiTests.test_model_upload_manifest_respects_sandbox_selection()`

**Purpose:** Test model-facing upload manifests do not expose sandbox paths unless selected.

#### `def UploadFilesApiTests.test_uploaded_file_prompt_block_hides_disabled_sandbox_path()`

**Purpose:** Test the private prompt block only includes sandbox path when allowed.

#### `def UploadFilesApiTests.test_uploaded_archive_prompt_block_says_preview_not_extracted()`

**Purpose:** Verify uploaded archive prompt block says preview not extracted.

#### `def UploadFilesApiTests.test_uploaded_file_ids_are_normalized_from_request_shapes()`

**Purpose:** Test upload file ids can be read from current and future request shapes.

#### `def UploadFilesApiTests.test_uploaded_file_context_entry_round_trips_file_ids()`

**Purpose:** Test upload ids can be persisted on a user message for regenerate/history replay.

#### `def UploadFilesApiTests.test_selected_tools_include_sandbox_only_when_resolved()`

**Purpose:** Test sandbox state is derived only from resolved tool servers.

#### `def UploadRoutingTests.test_display_kind_routes_known_file_types()`

**Purpose:** Test routing common file types to stable card labels.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def UploadRoutingTests.test_display_kind_routes_unknown_extension_to_file()`

**Purpose:** Test unknown extensions fall back to generic File, not rejection.

#### `def StaticCacheVersionTests.test_static_cache_version_format()`

**Purpose:** Verify static cache version format.

#### `def StaticCacheVersionTests.test_static_template_tag_appends_cache_bust_query()`

**Purpose:** Verify static template tag appends the cache-bust query.

#### `def MainViewTests.test_main_view_includes_runtime_settings_and_local_servers(_mock_engine)`

**Purpose:** Verify main view includes runtime settings and local servers.

**Steps:**

1. Return the computed result to the caller.

#### `def OllamaOptionMappingTests.test_prepare_chat_kwargs_maps_think_level_into_think()`

**Purpose:** Test prepare chat kwargs maps think level into think.

#### `def OllamaOptionMappingTests.test_prepare_chat_kwargs_drops_runtime_options_unsupported_by_current_ollama()`

**Purpose:** Test prepare chat kwargs drops runtime options unsupported by current Ollama.

#### `def OllamaOptionMappingTests.test_prepare_chat_kwargs_ignores_lms_only_internal_keys()`

**Purpose:** Test prepare chat kwargs ignores LM Studio only internal keys.

#### `def OllamaOptionMappingTests.test_prepare_runtime_passes_requested_engine_to_managed_service(mock_get_service)`

**Purpose:** Verify prepare runtime passes requested engine to managed service.

#### `def OllamaModelInfoTests.test_ollama_capabilities_without_tools_disable_tool_support()`

**Purpose:** Test an explicit Ollama capabilities list without tools disables tool support.

#### `def OllamaModelInfoTests.test_ollama_tools_capability_enables_tool_support()`

**Purpose:** Test Ollama's tools capability enables support without template markers.

#### `def OllamaModelInfoTests.test_ollama_tool_template_fallback_when_capabilities_are_missing()`

**Purpose:** Test old/custom Ollama responses can still infer tools from the template.

#### `def OpenAiOptionMappingTests.test_maps_supported_options_and_keeps_custom_values_in_extra_body()`

**Purpose:** Test maps supported options and keeps custom values in extra body.

#### `def OpenAiOptionMappingTests.test_openai_client_uses_placeholder_api_key_when_not_configured(_mock_api_key, _mock_engine_url, mock_openai_client)`

**Purpose:** Verify openai client uses placeholder api key when not configured.

#### `def OpenAiAdapterTests.test_get_model_settings_reads_openai_capabilities_and_reasoning(mock_get_client)`

**Purpose:** Verify get model settings reads openai capabilities and reasoning.

#### `def OpenAiAdapterTests.test_get_model_settings_reads_direct_feature_flags_and_scalar_supported_parameters(mock_get_client)`

**Purpose:** Verify get model settings reads direct feature flags and scalar supported parameters.

#### `def OpenAiAdapterTests.test_generate_stream_parses_reasoning_and_visible_content(mock_get_client)`

**Purpose:** Verify generate stream parses reasoning and visible content.

#### `def OpenAiAdapterTests.test_generate_stream_does_not_duplicate_plain_content_into_thinking(mock_get_client)`

**Purpose:** Verify generate stream does not duplicate plain content into thinking.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def OpenAiAdapterTests.test_get_model_settings_reads_companion_metadata_without_generation(mock_get_client, mock_get_companion_payload)`

**Purpose:** Verify get model settings reads companion metadata without generation.

#### `def GoogleGenAiAdapterTests.setUp()`

**Purpose:** Set up the test fixture.

#### `def GoogleGenAiAdapterTests.tearDown()`

**Purpose:** Tear down the test fixture.

#### `def GoogleGenAiAdapterTests.test_function_call_history_preserves_thought_signature()`

**Purpose:** Test Gemini function-call replay preserves thought signatures.

#### `def GoogleGenAiAdapterTests.test_preserved_function_call_parts_avoid_unsigned_duplicate()`

**Purpose:** Test fallback function-call reconstruction is skipped for preserved Gemini parts.

**Steps:**

1. Iterate and transform or accumulate state.
2. Parse or serialize JSON payloads.

#### `def GoogleGenAiAdapterTests.test_unsigned_legacy_function_call_history_is_skipped()`

**Purpose:** Test legacy unsigned Gemini tool-call transcript is not replayed.

**Steps:**

1. Iterate and transform or accumulate state.
2. Parse or serialize JSON payloads.

#### `def GoogleGenAiAdapterTests.test_get_models_filters_out_non_generate_content_models(mock_get_client, _mock_close_client)`

**Purpose:** Verify get models filters out non generate content models.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def GoogleGenAiAdapterTests.test_get_models_hides_zero_quota_models_for_current_key_after_runtime_learning(_mock_api_key, _mock_engine_url, mock_get_client, _mock_close_client)`

**Purpose:** Verify get models hides zero quota models for current key after runtime learning.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def GoogleGenAiAdapterTests.test_get_models_keeps_temporarily_rate_limited_models_visible(_mock_api_key, _mock_engine_url, mock_get_client, _mock_close_client)`

**Purpose:** Verify get models keeps temporarily rate limited models visible.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def GoogleGenAiAdapterTests.test_get_model_settings_returns_toggle_when_thinking_level_is_unsupported(mock_get_client, _mock_close_client)`

**Purpose:** Verify get model settings returns toggle when thinking level is unsupported.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def GoogleGenAiAdapterTests.test_generate_retries_without_thinking_level_when_model_rejects_it(mock_get_client, _mock_close_client)`

**Purpose:** Verify generate retries without thinking level when model rejects it.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def GoogleGenAiAdapterTests.test_learned_availability_is_scoped_to_api_key(_mock_engine_url, mock_get_client, _mock_close_client)`

**Purpose:** Verify learned availability is scoped to api key.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def EngineRegistryTests.test_reload_model_raises_for_engines_without_reload_support()`

**Purpose:** Test reload model raises for engines without reload support.

#### `def EngineRegistryTests.test_get_models_prepares_runtime_before_listing(mock_get_engine_module, mock_prepare_runtime)`

**Purpose:** Verify get models prepares runtime before listing.

#### `def EngineRegistryTests.test_get_model_settings_prepares_runtime_before_loading_metadata(mock_get_engine_module, mock_prepare_runtime)`

**Purpose:** Verify get model settings prepares runtime before loading metadata.

#### `def EngineAvailabilitySettingsTests.tearDown()`

**Purpose:** Clear the settings cache between mocked settings snapshots.

#### `def EngineAvailabilitySettingsTests.test_supported_engines_only_includes_enabled_flags()`

**Purpose:** Test supported engines only includes enabled engine flags.

#### `def EngineAvailabilitySettingsTests.test_active_engine_falls_back_when_configured_engine_is_disabled()`

**Purpose:** Test disabled active engine falls back to the first enabled engine.

#### `def LmsAdapterTests.test_serialize_model_info_reads_nested_info_wrapper()`

**Purpose:** Test serialize model info reads nested info wrapper.

#### `def LmsAdapterTests.test_get_model_settings_uses_loaded_model_info_when_direct_lookup_fails(mock_get_client, _mock_close_client)`

**Purpose:** Verify get model settings uses loaded model info when direct lookup fails.

#### `def LmsAdapterTests.test_prepare_openai_prediction_options_keeps_lms_custom_values_in_extra_body()`

**Purpose:** Test prepare OpenAI prediction options keeps LM Studio custom values in extra body.

#### `def ViewFormattingTests.test_strip_llm_control_tokens_removes_service_markers()`

**Purpose:** Test strip LLM control tokens removes service markers.

#### `def ViewFormattingTests.test_format_runtime_error_hides_lms_model_load_verbosity()`

**Purpose:** Test format runtime error hides LM Studio model load verbosity.

#### `def ViewFormattingTests.test_build_chat_title_handles_long_and_attachment_only_messages()`

**Purpose:** Test chat titles are compact and useful for attachment-only threads.

#### `def ViewFormattingTests.test_parse_active_tool_slugs_supports_json_and_legacy_values()`

**Purpose:** Test active tool slugs support both current JSON and legacy string shapes.

#### `def ViewFormattingTests.test_shared_file_tool_result_keeps_ui_metadata()`

**Purpose:** Test shared files keep their UI render payload after tool result splitting.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def ViewFormattingTests.test_build_activity_segments_keeps_repeated_share_file_aliases()`

**Purpose:** Test repeated tool aliases preserve all shared files in activity segments.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def BrowserPortalApiTests.test_active_browser_portal_state_uses_deadline_when_available()`

**Purpose:** Verify active browser portal state uses deadline when available.

#### `def BrowserPortalApiTests.test_finish_event_response_reports_done_and_queues_event()`

**Purpose:** Verify finish event response reports done and queues event.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def ModelInfoCacheTests.setUp()`

**Purpose:** Clear metadata caches around each test.

#### `def ModelInfoCacheTests.tearDown()`

**Purpose:** Restore metadata cache state after the test.

#### `def ModelInfoCacheTests.test_model_info_payload_cache_returns_detached_copies(mock_get_model_settings)`

**Purpose:** Verify model info payload cache returns detached copies.

#### `def ContextCompressionBudgetTests.test_history_budget_uses_same_model_token_estimator_as_usage_ui()`

**Purpose:** Verify history budget uses same model token estimator as usage ui.

#### `def ContextCompressionBudgetTests.test_history_budget_blends_observed_token_ratio()`

**Purpose:** Verify history budget blends observed token ratio.

#### `def ChatApiTests.setUp()`

**Purpose:** Set up the test fixture.

#### `def ChatApiTests.test_chat_api_rejects_invalid_json_body()`

**Purpose:** Test chat API rejects invalid JSON before touching runtime services.

#### `def ChatApiTests.test_chat_api_rejects_missing_model()`

**Purpose:** Test chat API requires a model name.

#### `def ChatApiTests.test_chat_api_creates_new_chat_and_streams_response(_mock_engine, mock_generate, mock_prepare_runtime)`

**Purpose:** Verify chat api creates new chat and streams response.

**Steps:**

1. Read or write Django ORM records.

#### `def ChatApiTests.test_chat_api_creates_attachment_only_thread(_mock_engine, mock_generate, _mock_prepare_runtime)`

**Purpose:** Verify chat api creates attachment only thread.

**Steps:**

1. Read or write Django ORM records.
2. Parse or serialize JSON payloads.

#### `def ChatApiTests.test_chat_api_passes_selected_tool_server_to_ollama(_mock_engine, mock_generate, _mock_prepare_runtime, _mock_model_settings)`

**Purpose:** Verify chat api passes selected tool server to ollama.

**Steps:**

1. Return the computed result to the caller.
2. Read or write Django ORM records.

#### `def ChatApiTests.test_chat_api_rejects_unknown_tool_server(_mock_engine)`

**Purpose:** Verify chat api rejects unknown tool server.

#### `def ChatApiTests.test_chat_api_stream_includes_server_and_tool_markers(_mock_engine, mock_generate, _mock_prepare_runtime)`

**Purpose:** Verify chat api stream includes server and tool markers.

#### `def ChatApiTests.test_chat_api_persists_reasoning_only_response(_mock_engine, mock_generate, _mock_prepare_runtime)`

**Purpose:** Verify chat api persists reasoning only response.

**Steps:**

1. Read or write Django ORM records.

#### `def ChatApiTests.test_chat_api_buffers_reasoning_while_streaming(_mock_engine, mock_generate, _mock_prepare_runtime)`

**Purpose:** Verify chat api buffers reasoning while streaming.

**Steps:**

1. Read or write Django ORM records.

#### `def ChatApiTests.test_stream_chat_response_auto_compresses_at_reasoning_safe_point(mock_generate, _mock_prepare_runtime, mock_build_compression_event)`

**Purpose:** Verify stream chat response auto compresses at reasoning safe point.

**Steps:**

1. Read or write Django ORM records.

#### `def ChatApiTests.test_stream_chat_response_auto_compresses_at_tool_call_safe_point(mock_generate, _mock_prepare_runtime, mock_build_compression_event)`

**Purpose:** Verify stream chat response auto compresses at tool call safe point.

**Steps:**

1. Read or write Django ORM records.

#### `def ChatApiTests.test_build_chat_history_compresses_when_current_prompt_crosses_threshold(mock_build_summary)`

**Purpose:** Verify build chat history compresses when current prompt crosses threshold.

**Steps:**

1. Read or write Django ORM records.

#### `def ChatApiTests.test_chat_api_persists_generic_attachments_and_builds_lms_messages(_mock_engine, mock_generate, _mock_prepare_runtime)`

**Purpose:** Verify chat api persists generic attachments and builds lms messages.

**Steps:**

1. Read or write Django ORM records.
2. Parse or serialize JSON payloads.

#### `def ChatApiTests.test_chat_api_rejects_tool_server_when_lms_model_lacks_tool_support(_mock_engine, _mock_model_settings, _mock_preset_model_settings)`

**Purpose:** Verify chat api rejects tool server when lms model lacks tool support.

**Steps:**

1. Return the computed result to the caller.

#### `def ChatApiTests.test_chat_api_rejects_tool_server_when_ollama_capabilities_omit_tools(_mock_engine, _mock_model_settings)`

**Purpose:** Verify chat api rejects tool server when ollama capabilities omit tools.

**Steps:**

1. Return the computed result to the caller.

#### `def ChatApiTests.test_chat_api_rejects_tool_server_when_openai_model_lacks_tool_support(_mock_engine, _mock_model_settings)`

**Purpose:** Verify chat api rejects tool server when openai model lacks tool support.

**Steps:**

1. Return the computed result to the caller.

#### `def ChatApiTests.test_chat_api_saves_visible_content_and_machine_transcript(_mock_engine, mock_generate, _mock_prepare_runtime)`

**Purpose:** Verify chat api saves visible content and machine transcript.

**Steps:**

1. Read or write Django ORM records.

#### `def ChatApiTests.test_chat_api_uses_stored_transcript_for_follow_up_messages(_mock_engine, mock_generate, _mock_prepare_runtime)`

**Purpose:** Verify chat api uses stored transcript for follow up messages.

**Steps:**

1. Iterate and transform or accumulate state.
2. Read or write Django ORM records.

#### `def ChatApiTests.test_chat_api_strips_legacy_ui_markup_when_transcript_is_missing(_mock_engine, mock_generate, _mock_prepare_runtime)`

**Purpose:** Verify chat api strips legacy ui markup when transcript is missing.

**Steps:**

1. Iterate and transform or accumulate state.
2. Read or write Django ORM records.

#### `def ChatApiTests.test_chat_api_strips_service_control_tokens_from_visible_output(_mock_engine, mock_generate, _mock_prepare_runtime)`

**Purpose:** Verify chat api strips service control tokens from visible output.

**Steps:**

1. Read or write Django ORM records.

#### `def LlmApiRuntimeSyncTests.test_sync_prepares_enabled_and_cleans_up_disabled(_mock_enabled, mock_prepare, mock_cleanup)`

#### `def LlmApiRuntimeSyncTests.test_handle_engine_transition_calls_sync(mock_sync)`

#### `def OllamaDesiredStateTests.test_desired_state_runs_when_enabled_even_if_active_engine_differs(_mock_get, _mock_active)`

#### `def RequestEngineResolutionTests._build_request(query)`

#### `def RequestEngineResolutionTests.test_resolve_defaults_to_active_engine(_mock_active)`

#### `def RequestEngineResolutionTests.test_resolve_query_engine_when_enabled(_mock_enabled)`

#### `def RequestEngineResolutionTests.test_resolve_rejects_disabled_engine(_mock_enabled)`

#### `def RequestEngineResolutionTests.test_body_engine_takes_priority_over_query(_mock_enabled)`

#### `def DisabledEngineApiTests.isolated_settings_payload(payload)`

#### `def DisabledEngineApiTests.test_models_api_rejects_disabled_engine()`

#### `def DisabledEngineApiTests.test_chat_api_accepts_engine_query_param(mock_generate, _mock_prepare_runtime)`

#### `def RuntimeSettingsApiTests.setUp()`

#### `def RuntimeSettingsApiTests.tearDown()`

#### `def RuntimeSettingsApiTests.isolated_settings_payload(payload)`

**Purpose:** Isolated settings payload.

#### `def RuntimeSettingsApiTests.test_get_runtime_settings_payload()`

**Purpose:** Test get runtime settings payload.

#### `def RuntimeSettingsApiTests.test_runtime_settings_rejects_invalid_json()`

**Purpose:** Test runtime settings rejects invalid JSON.

#### `def RuntimeSettingsApiTests.test_post_runtime_settings_updates_engine(mock_transition)`

**Purpose:** Verify post runtime settings updates engine.

#### `def RuntimeSettingsApiTests.test_post_runtime_settings_ignores_disabled_engine(mock_transition)`

**Purpose:** Verify post runtime settings ignores disabled engine.

#### `def RuntimeSettingsApiTests.test_models_api_returns_engine_specific_models(mock_models)`

**Purpose:** Verify models api returns engine specific models.

#### `def RuntimeSettingsApiTests.test_model_info_api_requires_model_parameter()`

**Purpose:** Test model info API requires a model query parameter.

#### `def RuntimeSettingsApiTests.test_model_info_api_returns_501_for_unimplemented_engines(mock_build_payload)`

**Purpose:** Verify model info api returns 501 for unimplemented engines.

#### `def RuntimeSettingsApiTests.test_inference_info_api_returns_unified_payload(mock_build_payload)`

**Purpose:** Verify inference info api returns unified payload.

#### `def RuntimeSettingsApiTests.test_inference_info_api_uses_runtime_selected_model(mock_build_payload)`

**Purpose:** Verify inference info api uses runtime selected model.

#### `def RuntimeSettingsApiTests.test_runtime_settings_payload_does_not_expose_api_key(_mock_runtime_settings, _mock_engines)`

**Purpose:** Verify runtime settings payload does not expose api key.

#### `def ToolApiTests.setUp()`

#### `def ToolApiTests.tearDown()`

#### `def ToolApiTests.test_tools_api_returns_discovered_servers()`

**Purpose:** Test tools API returns discovered servers.

**Steps:**

1. Return the computed result to the caller.

#### `def ToolApiTests.test_load_chat_api_returns_active_tool_server_id()`

**Purpose:** Test load chat API returns active tool server id.

**Steps:**

1. Read or write Django ORM records.

#### `def ToolApiTests.test_load_chat_api_returns_multiple_active_tool_server_ids()`

**Purpose:** Test load chat API returns all active tool server ids.

**Steps:**

1. Read or write Django ORM records.

#### `def ToolApiTests.test_load_chat_api_returns_attachment_metadata_without_inline_data()`

**Purpose:** Test load chat API returns attachment metadata without inline data.

**Steps:**

1. Read or write Django ORM records.

#### `def ToolApiTests.test_attachment_content_api_streams_stored_bytes()`

**Purpose:** Test attachment content API streams stored bytes on demand.

**Steps:**

1. Read or write Django ORM records.

#### `def ToolApiTests.test_attachment_content_api_streams_legacy_image_bytes()`

**Purpose:** Test attachment content API streams legacy image records.

**Steps:**

1. Read or write Django ORM records.

#### `def ToolApiTests.test_attachment_content_api_rejects_unknown_record_type()`

**Purpose:** Test attachment content API rejects unknown record types.

#### `def ToolApiTests.test_delete_last_assistant_api_returns_user_message_for_regeneration()`

**Purpose:** Test delete last assistant API returns the user message to regenerate.

**Steps:**

1. Read or write Django ORM records.

#### `def ToolApiTests.test_delete_last_assistant_api_rejects_when_last_message_is_user()`

**Purpose:** Test delete last assistant API rejects chats ending with a user message.

**Steps:**

1. Read or write Django ORM records.

#### `def ToolApiTests.test_delete_message_api_removes_selected_message()`

**Purpose:** Test delete message API removes only the selected message.

**Steps:**

1. Read or write Django ORM records.

#### `def ToolApiTests.test_rename_chat_api_updates_title()`

**Purpose:** Test rename chat API trims and persists the title.

**Steps:**

1. Read or write Django ORM records.

#### `def ToolApiTests.test_delete_chat_api_removes_thread_and_messages()`

**Purpose:** Test delete chat API removes the whole thread.

**Steps:**

1. Read or write Django ORM records.

#### `def OllamaPresetApiTests.setUp()`

#### `def OllamaPresetApiTests.tearDown()`

#### `def OllamaPresetApiTests.test_model_info_includes_active_ollama_preset_defaults_and_servers(mock_get_model_settings)`

**Purpose:** Verify model info includes active ollama preset defaults and servers.

**Steps:**

1. Return the computed result to the caller.
2. Read or write Django ORM records.

#### `def OllamaPresetApiTests.test_sync_endpoint_clones_default_preset_on_first_change()`

**Purpose:** Test sync endpoint clones default preset on first change.

**Steps:**

1. Read or write Django ORM records.

#### `def OllamaPresetApiTests.test_create_rename_delete_endpoints_manage_custom_preset()`

**Purpose:** Test create rename delete endpoints manage custom preset.

**Steps:**

1. Read or write Django ORM records.

#### `def OllamaPresetApiTests.test_duplicate_preset_name_returns_validation_error()`

**Purpose:** Test duplicate preset name returns validation error.

#### `def OllamaPresetApiTests.test_select_endpoint_activates_custom_preset()`

**Purpose:** Test select endpoint activates an existing custom preset.

**Steps:**

1. Read or write Django ORM records.

#### `def OllamaPresetApiTests.test_default_preset_mutation_errors_return_400()`

**Purpose:** Test default preset mutation errors are returned as validation responses.

**Steps:**

1. Read or write Django ORM records.

#### `def LmsPresetApiTests.setUp()`

#### `def LmsPresetApiTests.tearDown()`

#### `def LmsPresetApiTests.test_model_info_includes_active_lms_preset_defaults(mock_preset_settings, mock_model_settings)`

**Purpose:** Verify model info includes active lms preset defaults.

**Steps:**

1. Read or write Django ORM records.

#### `def LmsPresetApiTests.test_sync_endpoint_clones_default_lms_preset_on_first_change(mock_get_model_settings)`

**Purpose:** Verify sync endpoint clones default lms preset on first change.

**Steps:**

1. Read or write Django ORM records.

#### `def LmsPresetApiTests.test_get_lms_presets_requires_model()`

**Purpose:** Test get LM Studio presets endpoint requires a model.

#### `def LmsPresetApiTests.test_create_rename_delete_endpoints_manage_custom_lms_preset(mock_get_model_settings)`

**Purpose:** Verify create rename delete endpoints manage custom lms preset.

**Steps:**

1. Read or write Django ORM records.

#### `def LmsPresetApiTests.test_duplicate_lms_preset_name_returns_validation_error(mock_get_model_settings)`

**Purpose:** Verify duplicate lms preset name returns validation error.

#### `def LmsPresetApiTests.test_select_endpoint_activates_custom_lms_preset(mock_get_model_settings)`

**Purpose:** Verify select endpoint activates custom lms preset.

**Steps:**

1. Read or write Django ORM records.

#### `def LmsPresetApiTests.test_default_lms_preset_mutation_errors_return_400(mock_get_model_settings)`

**Purpose:** Verify default lms preset mutation errors return 400.

**Steps:**

1. Read or write Django ORM records.

#### `def MessageIdAndRegenerateTests.setUp()`

**Purpose:** Prepare shared fixtures for each test case.

#### `def MessageIdAndRegenerateTests.test_chat_api_returns_message_id_headers(_mock_engine, mock_generate, _mock_runtime)`

**Purpose:** Verify chat api returns message id headers.

**Steps:**

1. Read or write Django ORM records.

#### `def MessageIdAndRegenerateTests.test_regenerate_does_not_duplicate_user_message(_mock_engine, mock_generate, _mock_runtime)`

**Purpose:** Verify regenerate does not duplicate user message.

**Steps:**

1. Read or write Django ORM records.

#### `def MessageIdAndRegenerateTests.test_chat_updated_at_is_bumped_after_generation(_mock_engine, mock_generate, _mock_runtime)`

**Purpose:** Verify chat updated at is bumped after generation.

**Steps:**

1. Read or write Django ORM records.

---

## Private functions

#### `def SkillsModelContextTests._assert_has_skills_inventory(text, *folders) -> None`

**Purpose:** Assert has skills inventory.

#### `def SkillsModelContextTests._assert_no_skill_context(text) -> None`

**Purpose:** Assert no skill context.

#### `def SkillsModelContextTests._assert_config_update_header(text) -> None`

**Purpose:** Assert config update header.

#### `def SkillsModelContextTests._write_skill(folder, *, enabled=…, title=…) -> None`

**Purpose:** Write skill.

#### `def SkillsModelContextTests._compose(*, consume=…, include_baseline=…, user_prompt=…) -> str`

**Purpose:** Compose.

**Steps:**

1. Return the computed result to the caller.

#### `def SkillsModelContextTests._system_message_for_chat(system_prompt, user_text) -> str`

**Purpose:** System message for chat.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.
3. Read or write Django ORM records.

#### `def SkillsModelContextTests._disable_via_api(folder) -> None`

**Purpose:** Disable via api.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def EngineAvailabilitySettingsTests._with_settings_payload(payload, assertion)`

**Purpose:** Run one assertion block against an isolated settings payload.

---

## Related

- [UI/_index](../../_index/)
