---
title: "views"
draft: false
---

## Module `views`

`Apps/UI/views.py` — HTTP layer for pages and chat APIs.

---

## Overview

Django views and `/api/*` JSON handlers for the chat UI: streaming `chat_api`, uploads, presets, skills, MCP config, runtime settings, browser portal, and context compression hooks.


---

## Classes

### `class MainView`

**Purpose:** Type `MainView` defined in `views.py`.

### `class ProfileView`

**Purpose:** Type `ProfileView` defined in `views.py`.

### `class ChatView`

**Purpose:** Type `ChatView` defined in `views.py`.

---

## Public functions

#### `def MainView.get_context_data(**kwargs) -> dict[str, Any]`

**Purpose:** Build the main page context.

#### `def upload_files_api(request)`

**Purpose:** Store uploaded files and return UI-facing file cards.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.
5. Build an HTTP response for the client.

#### `def chat_api(request)`

**Purpose:** Handle a chat generation request.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Read or write Django ORM records.
5. Parse or serialize JSON payloads.
6. Build an HTTP response for the client.

#### `def uploaded_file_content_api(request, file_id)`

**Purpose:** Return uploaded file bytes on demand.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def shared_file_download_api(request)`

**Purpose:** Download a model-shared local file after validating its workspace path.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def abort_generation_api(request)`

**Purpose:** Abort active generation.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def attachment_content_api(request, record_type, attachment_id)`

**Purpose:** Return stored attachment bytes on demand.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Read or write Django ORM records.
4. Build an HTTP response for the client.

#### `def delete_message_api(request, message_id)`

**Purpose:** Delete a specific message by ID.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Read or write Django ORM records.
4. Build an HTTP response for the client.

#### `def delete_last_assistant_api(request, chat_id)`

**Purpose:** Delete the last assistant reply for regeneration.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Read or write Django ORM records.
5. Build an HTTP response for the client.

#### `def regenerate_chat_api(request, chat_id)`

**Purpose:** Regenerate the assistant reply for an existing user message without duplicating it.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Read or write Django ORM records.
5. Parse or serialize JSON payloads.
6. Build an HTTP response for the client.

#### `def rename_chat_api(request, chat_id)`

**Purpose:** Rename a chat thread.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Read or write Django ORM records.
4. Build an HTTP response for the client.

#### `def delete_chat_api(request, chat_id)`

**Purpose:** Delete a chat thread and all its messages.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Read or write Django ORM records.
4. Build an HTTP response for the client.

#### `def load_chat_api(request, chat_id)`

**Purpose:** Load persisted messages for a chat thread.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Read or write Django ORM records.
5. Build an HTTP response for the client.

#### `def get_model_info_api(request)`

**Purpose:** Return model metadata for the selected engine.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Build an HTTP response for the client.

#### `def get_inference_info_api(request)`

**Purpose:** Return unified runtime inference metadata for the active engine/model.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Build an HTTP response for the client.

#### `def get_models_api(request)`

**Purpose:** Return the model list for the selected engine.

**Steps:**

1. Return the computed result to the caller.
2. Build an HTTP response for the client.

#### `def mcp_config_api(request)`

**Purpose:** Return discovered tool servers.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def skills_api(request)`

**Purpose:** List skills or create a new skill folder.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def skills_folder_api(request)`

**Purpose:** Rename or delete one skill folder.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def skills_file_api(request)`

**Purpose:** Read, write, or delete one skill file.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def skills_enabled_api(request)`

**Purpose:** Enable or disable one skill.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def skills_directory_api(request)`

**Purpose:** Create or delete a subdirectory inside a skill folder.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def skills_import_api(request)`

**Purpose:** Import a skill folder from a list of {path, content} file entries.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def skills_path_api(request)`

**Purpose:** Rename a file or directory inside a skill folder.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def get_tools_api(request)`

**Purpose:** Return locally discovered MCP-style tool servers for the requested engine/model.

**Steps:**

1. Return the computed result to the caller.
2. Build an HTTP response for the client.

#### `def favicon_api(request)`

**Purpose:** Resolve and proxy a stable favicon for a search result domain.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.
3. Build an HTTP response for the client.

#### `def get_ollama_presets_api(request)`

**Purpose:** Return Ollama preset metadata.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Build an HTTP response for the client.

#### `def get_context_usage_api(request)`

**Purpose:** Return estimated/observed context usage for the current chat and model.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Read or write Django ORM records.
4. Build an HTTP response for the client.

#### `def context_compress_api(request)`

**Purpose:** Force or opportunistically run context compression and persist a timeline marker.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Read or write Django ORM records.
4. Build an HTTP response for the client.

#### `def get_lms_presets_api(request)`

**Purpose:** Return preset metadata for the selected LM Studio model.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Build an HTTP response for the client.

#### `def sync_ollama_preset_api(request)`

**Purpose:** Sync the active Ollama preset.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def sync_lms_preset_api(request)`

**Purpose:** Persist UI changes to the active LM Studio preset.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def select_ollama_preset_api(request)`

**Purpose:** Activate an Ollama preset.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def select_lms_preset_api(request)`

**Purpose:** Set the active preset for an LM Studio model.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def create_ollama_preset_api(request)`

**Purpose:** Create an Ollama preset.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def create_lms_preset_api(request)`

**Purpose:** Create a new LM Studio preset for the selected model.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def rename_ollama_preset_api(request)`

**Purpose:** Rename an Ollama preset.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def rename_lms_preset_api(request)`

**Purpose:** Rename an existing custom LM Studio preset.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def delete_ollama_preset_api(request)`

**Purpose:** Delete an Ollama preset.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def delete_lms_preset_api(request)`

**Purpose:** Delete an existing custom preset and fall back to the default one.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Build an HTTP response for the client.

#### `def runtime_settings_api(request)`

**Purpose:** Read or update runtime settings.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Build an HTTP response for the client.

#### `def browser_portal_frame_api(request)`

**Purpose:** Return the latest frame published by browser_wait_for_user.

**Steps:**

1. Return the computed result to the caller.
2. Build an HTTP response for the client.

#### `def browser_portal_event_api(request)`

**Purpose:** Queue one human portal event for the active browser_wait_for_user loop.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.
4. Build an HTTP response for the client.

#### `def ProfileView.get_context_data(**kwargs) -> dict[str, Any]`

**Purpose:** Build the profile page context.

#### `def ChatView.get_context_data(**kwargs) -> dict[str, Any]`

**Purpose:** Build the preloaded chat page context.

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _read_default_system_prompt() -> str`

**Purpose:** Read the project-level system prompt file.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _build_runtime_context() -> str`

**Purpose:** Build dynamic runtime context injected into every system prompt.

#### `def _normalize_favicon_domain(value) -> str`

**Purpose:** Normalize one domain string for favicon lookup.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _is_public_favicon_host(host) -> bool`

**Purpose:** Return whether the host resolves to a public address.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _favicon_url_is_safe(url) -> bool`

**Purpose:** Return whether one favicon URL is safe to fetch.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _favicon_content_type(response, content) -> str`

**Purpose:** Infer the favicon MIME type from headers and bytes.

**Steps:**

1. Return the computed result to the caller.

#### `def _favicon_safe_get(session, url, *, stream=…) -> Any | None`

**Purpose:** Perform one bounded HTTP GET with redirect validation.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _fetch_favicon_candidate(session, url) -> tuple[str, bytes] | None`

**Purpose:** Download one favicon candidate when it is within size limits.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _score_favicon_candidate(candidate) -> int`

**Purpose:** Rank one favicon candidate by rel, size, and format.

**Steps:**

1. Return the computed result to the caller.

#### `def _collect_favicon_candidates(session, base_url) -> list[dict[str, str]]`

**Purpose:** Collect favicon candidates from HTML, manifests, and fallbacks.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _resolve_favicon_content(domain) -> tuple[str, bytes] | None`

**Purpose:** Resolve the best favicon bytes for one domain.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _favicon_cache_paths(domain) -> tuple[Path, Path]`

**Purpose:** Return on-disk cache paths for one favicon domain.

#### `def _read_favicon_disk_cache(domain, now) -> tuple[str, bytes] | None`

**Purpose:** Read a cached favicon when the entry is still valid.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _write_favicon_disk_cache(domain, content_type, content, expires_at) -> None`

**Purpose:** Persist one favicon payload to the disk cache.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.
3. Parse or serialize JSON payloads.

#### `def _chat_is_first_user_turn(chat) -> bool`

**Purpose:** Return whether the chat has not yet persisted a user message.

#### `def _compose_system_prompt(user_system_prompt, *, consume_skill_notifications=…, include_skills_baseline=…) -> str`

**Purpose:** Merge the project prompt with per-request user instructions.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _engine_metadata_scope(engine) -> tuple[str, str]`

**Purpose:** Return a stable runtime scope for model metadata caches.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _clone_metadata_payload(payload) -> Any`

**Purpose:** Return a defensive deep copy of a cacheable payload.

#### `def _clear_model_metadata_caches() -> None`

**Purpose:** Clear cached model metadata.

#### `def _clear_tool_server_cache() -> None`

**Purpose:** Drop cached tool server lists only (e.g. after ``mcp.json`` changes).

#### `def _remember_active_model(engine, model_name) -> None`

**Purpose:** Remember the latest selected model for one engine.

#### `def _get_remembered_active_model(engine) -> str`

**Purpose:** Read the latest selected model for one engine.

#### `def _coerce_positive_int(value) -> int | None`

**Purpose:** Convert one value into a positive integer when possible.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _first_positive_int(mapping, keys) -> int | None`

**Purpose:** Read the first positive integer from a mapping.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _resolve_inference_model(engine, requested_model) -> tuple[str, str]`

**Purpose:** Resolve the model name represented by an inference-info request.

**Steps:**

1. Return the computed result to the caller.

#### `def _get_cached_model_info(engine, model_name) -> dict[str, Any] | None`

**Purpose:** Return cached model info when it is still fresh.

**Steps:**

1. Return the computed result to the caller.

#### `def _set_cached_model_info(engine, model_name, payload) -> dict[str, Any]`

**Purpose:** Store model info in the runtime cache.

**Steps:**

1. Return the computed result to the caller.

#### `def _get_cached_model_list(engine) -> list[str] | None`

**Purpose:** Return cached model names when still fresh.

**Steps:**

1. Return the computed result to the caller.

#### `def _set_cached_model_list(engine, models) -> list[str]`

**Purpose:** Store model names in the runtime cache.

**Steps:**

1. Return the computed result to the caller.

#### `def _list_tool_servers_cached(engine, model_name) -> list[dict[str, Any]]`

**Purpose:** Return cached tool servers when still fresh.

**Steps:**

1. Return the computed result to the caller.

#### `def _print_runtime_event(message) -> None`

**Purpose:** Emit one concise runtime event for the ASLM console.

#### `def _is_expected_runtime_error(exc) -> bool`

**Purpose:** Return whether the exception is an expected runtime/connectivity failure.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _format_runtime_error(engine, exc) -> str`

**Purpose:** Return a user-facing runtime error string without noisy transport details.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _strip_llm_control_tokens(content) -> str`

**Purpose:** Remove assistant-control tokens that should never be shown to the user.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _summarize_option_keys(options, max_keys) -> str`

**Purpose:** Return a short, readable summary of option keys.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _count_request_images(messages) -> int`

**Purpose:** Count image attachments present in the current outbound request.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _decode_base64_payload(raw_value) -> bytes`

**Purpose:** Return decoded bytes for one base64 payload or data URL.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _estimate_base64_payload_size(raw_value) -> int`

**Purpose:** Estimate decoded byte size without materializing the full payload.

**Steps:**

1. Return the computed result to the caller.

#### `def _is_valid_base64_payload(raw_value) -> bool`

**Purpose:** Return whether one payload is structurally valid base64.

**Steps:**

1. Return the computed result to the caller.

#### `def _parse_data_url(raw_value) -> tuple[str, str]`

**Purpose:** Split a data URL into MIME type and base64 payload.

**Steps:**

1. Return the computed result to the caller.

#### `def _guess_attachment_kind(mime_type, name) -> str`

**Purpose:** Return the normalized attachment kind for the payload.

**Steps:**

1. Return the computed result to the caller.

#### `def _normalize_attachment_payload(raw_attachment, order) -> dict[str, Any] | None`

**Purpose:** Normalize one incoming attachment payload into the storage shape.

**Steps:**

1. Return the computed result to the caller.

#### `def _normalize_request_attachments(data) -> list[dict[str, Any]]`

**Purpose:** Return a normalized list of request attachments.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _attachment_content_url(record_type, record_id) -> str`

**Purpose:** Build an attachment content endpoint path.

#### `def _serialize_attachment_record(attachment, *, include_data=…) -> dict[str, Any]`

**Purpose:** Convert a persisted attachment-like object into the frontend payload.

**Steps:**

1. Return the computed result to the caller.

#### `def _get_message_attachments(message, *, include_data=…) -> list[dict[str, Any]]`

**Purpose:** Return all persisted attachments for a message in a shared shape.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _attachment_data_to_bytes(attachment) -> bytes`

**Purpose:** Decode one serialized attachment payload into bytes.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _is_text_attachment(mime_type, name) -> bool`

**Purpose:** Return whether the attachment should be decoded as text.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _truncate_attachment_text(text, limit) -> str`

**Purpose:** Trim attachment text so prompts stay bounded.

**Steps:**

1. Return the computed result to the caller.

#### `def _cache_attachment_text(attachment, extracted_text) -> str`

**Purpose:** Persist extracted text for one stored file attachment.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Read or write Django ORM records.

#### `def _extract_attachment_text(attachment) -> str`

**Purpose:** Extract prompt-friendly text from a file attachment when possible.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _build_file_attachment_prompt_block(attachment) -> str`

**Purpose:** Serialize one non-image attachment into universal text context.

**Steps:**

1. Return the computed result to the caller.

#### `def _selected_tools_include_sandbox(selected_tool_servers) -> bool`

**Purpose:** Return whether the resolved tool selection includes sandbox file access.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _normalize_uploaded_file_ids(data) -> list[str]`

**Purpose:** Return uploaded file ids referenced by a chat request.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _load_model_upload_manifests(file_ids, *, sandbox_enabled) -> list[dict[str, Any]]`

**Purpose:** Load model-facing upload manifests for the selected tool state.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _upload_manifest_file_ids(manifests) -> list[str]`

**Purpose:** Return stable file ids from loaded upload manifests.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_uploaded_file_context_entry(file_ids) -> dict[str, Any] | None`

**Purpose:** Build a stored user-message entry that keeps upload context replayable.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_uploaded_file_ids_from_message(message) -> list[str]`

**Purpose:** Return upload ids persisted on a user message.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _load_message_upload_manifests(message, *, sandbox_enabled) -> list[dict[str, Any]]`

**Purpose:** Load persisted upload manifests for one stored user message.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_uploaded_file_prompt_block(manifest) -> str`

**Purpose:** Serialize one uploaded file manifest into private model context.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _apply_uploaded_file_manifests_to_llm_entry(entry, manifests) -> dict[str, Any]`

**Purpose:** Attach uploaded file manifests to the current user entry.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _apply_attachments_to_llm_entry(entry, attachments) -> dict[str, Any]`

**Purpose:** Attach images and file context to one outbound LLM message.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _get_local_gpu_devices() -> list[dict[str, Any]]`

**Purpose:** Read local GPU devices

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Spawn or communicate with a child process.

#### `def _get_active_engine(requested_engine) -> str`

**Purpose:** Resolve active engine

#### `def _extract_model_name(model_entry) -> str`

**Purpose:** Extract model name

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _load_models_for_engine(engine) -> list[str]`

**Purpose:** Load engine models

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _build_base_context() -> dict[str, Any]`

**Purpose:** Build shared template context

**Steps:**

1. Return the computed result to the caller.
2. Read or write Django ORM records.

#### `def _build_runtime_settings_payload() -> dict[str, Any]`

**Purpose:** Build runtime settings payload

**Steps:**

1. Return the computed result to the caller.

#### `def _build_chat_title(message, has_attachments) -> str`

**Purpose:** Build chat title

**Steps:**

1. Return the computed result to the caller.

#### `def _detect_image_mime(base64_data) -> str`

**Purpose:** Detect image MIME type

**Steps:**

1. Return the computed result to the caller.

#### `def _strip_llm_markup(content) -> str`

**Purpose:** Strip legacy markup

**Steps:**

1. Return the computed result to the caller.

#### `def _normalize_transcript_entries(raw_entries) -> list[dict[str, Any]]`

**Purpose:** Normalize transcript entries

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_llm_history_entries(message, *, sandbox_enabled=…) -> list[dict[str, Any]]`

**Purpose:** Build LLM history entries

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _message_has_context_compression_summary(message) -> bool`

**Purpose:** Return whether one stored assistant message represents a compression marker.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_context_compression_source_entries(history_records, *, sandbox_enabled=…) -> list[dict[str, Any]]`

**Purpose:** Build chronological non-compression entries represented by a new boundary.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_activity_segments(message) -> list[dict[str, Any]]`

**Purpose:** Build activity segments

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _message_has_reasoning_segments(message) -> bool`

**Purpose:** Return whether the stored transcript contains model reasoning.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _serialize_message(message, *, include_attachment_data=…) -> dict[str, Any]`

**Purpose:** Serialize message

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _extract_stream_message_parts(chunk) -> tuple[str, str]`

**Purpose:** Extract streamed message parts

**Steps:**

1. Return the computed result to the caller.

#### `def _copy_transcript_entries_for_storage(transcript_entries) -> list[dict[str, Any]]`

**Purpose:** Return transcript entries safe to persist while a response is streaming.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_streaming_assistant_transcript(transcript_entries, *, visible_content, thinking_content) -> list[dict[str, Any]]`

**Purpose:** Overlay streamed assistant text onto machine transcript entries.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _serialize_tool_call_marker(tool_event) -> str`

**Purpose:** Serialize tool marker

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

#### `def _serialize_tool_result_marker(alias, content, *, tool_ui=…, structured_content=…) -> str`

**Purpose:** Serialize tool result marker

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

#### `def _serialize_context_compression_marker(compression_event) -> str`

**Purpose:** Encode a context-compression boundary without pretending it is a model tool.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

#### `def _normalize_capability_tokens(capabilities) -> set[str]`

**Purpose:** Extract Ollama model info

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _ollama_template_supports_tool_calling(template) -> bool`

**Purpose:** Return whether one Ollama chat template can serialize tools.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _ollama_metadata_supports_tool_calling(capabilities, template) -> bool`

**Purpose:** Return whether Ollama metadata is strong enough to expose local tools.

**Steps:**

1. Return the computed result to the caller.

#### `def _extract_ollama_model_info(settings_data) -> dict[str, Any]`

**Purpose:** Parse Ollama-specific model metadata into a frontend-friendly payload.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _ollama_model_is_cloud(model_name, model_layers) -> bool`

**Purpose:** Decide whether an Ollama model runs in the cloud (no local layers to manage).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _extract_generic_model_info(settings_data) -> dict[str, Any]`

**Purpose:** Extract generic model info

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_fallback_model_info_payload(engine, model_name) -> dict[str, Any]`

**Purpose:** Build model info payload

**Steps:**

1. Return the computed result to the caller.

#### `def _build_model_info_payload(engine, model_name, *, allow_fallback=…) -> dict[str, Any]`

**Purpose:** Load adapter metadata and normalize it for the frontend.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _get_engine_label(engine) -> str`

**Purpose:** Build a stable engine label for API payloads.

#### `def _build_inference_info_payload(engine, model_name, model_info_payload, model_source) -> dict[str, Any]`

**Purpose:** Normalize model metadata into a compact runtime-inference payload.

**Steps:**

1. Return the computed result to the caller.

#### `def _runtime_metadata_source(name, route, port_setting) -> dict[str, Any]`

**Purpose:** Describe one local metadata source without freezing dynamic ports.

**Steps:**

1. Return the computed result to the caller.

#### `def _read_runtime_metadata_file() -> dict[str, Any]`

**Purpose:** Return runtime metadata file.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _write_runtime_metadata_file(payload) -> None`

**Purpose:** Write runtime metadata file.

#### `def _sync_runtime_model_metadata(engine, model_name, model_info_payload, *, source, route) -> None`

**Purpose:** Persist active model metadata for local tools in real time.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def _read_json_request_body(request) -> dict[str, Any]`

**Purpose:** Read JSON body

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Parse or serialize JSON payloads.

#### `def _resolve_tool_servers(engine, model_name, tool_server_ids) -> list[dict[str, Any]]`

**Purpose:** Resolve selected tool servers

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _validate_tool_server_support(engine, model_name, tool_server_ids, payload) -> None`

**Purpose:** Raise when tools are requested for a model that should not call tools.

**Steps:**

1. Raise on invalid input or failure conditions.

#### `def _parse_active_tool_slugs(slug) -> list[str]`

**Purpose:** Parse stored tool slugs

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _resolve_chat(chat_id, user_message, attachments) -> Chat`

**Purpose:** Resolve chat instance

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Read or write Django ORM records.

#### `def _store_message_attachments(message_record, attachments) -> None`

**Purpose:** Save message images

**Steps:**

1. Iterate and transform or accumulate state.
2. Read or write Django ORM records.

#### `def _resolve_history_char_budget(model_info_payload, *, active_engine=…, active_model=…, observed_chars_per_token=…) -> int`

**Purpose:** Resolve a bounded history budget from model metadata.

**Steps:**

1. Return the computed result to the caller.

#### `def _estimate_llm_entry_chars(entry) -> int`

**Purpose:** Estimate the prompt cost of one normalized LLM entry.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

#### `def _estimate_tokens_from_chars(char_count) -> int`

**Purpose:** Approximate token count from UTF-8 character count.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _model_chars_per_token_hint(*, model_info_payload, active_engine, active_model) -> float`

**Purpose:** Return one base chars/token hint from model family and engine metadata.

**Steps:**

1. Return the computed result to the caller.

#### `def _effective_chars_per_token_hint(*, model_info_payload, active_engine, active_model, observed_chars_per_token=…) -> float`

**Purpose:** Return the chars/token ratio shared by usage telemetry and compression.

**Steps:**

1. Return the computed result to the caller.

#### `def _history_char_budget_from_context_window(context_window_tokens, *, model_info_payload, active_engine, active_model, observed_chars_per_token=…, minimum_chars=…, fallback_chars=…) -> int`

**Purpose:** Convert a token context window into the same char budget the UI estimates.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _estimate_tokens_adaptive(*, char_count, model_info_payload, active_engine, active_model, observed_chars_per_token=…) -> int`

**Purpose:** Estimate tokens using model hints + optional observed prompt telemetry.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _context_window_tokens_from_model_info(model_info_payload) -> int`

**Purpose:** Context window tokens from model info.

**Steps:**

1. Return the computed result to the caller.

#### `def _estimate_context_usage(*, chat, system_prompt, draft_text, model_info_payload, active_engine=…, active_model=…) -> dict[str, Any]`

**Purpose:** Estimate current context usage for UI telemetry.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_manual_compression_event(*, chat, system_prompt, engine, model_name, model_info_payload, force, draft_text=…, exclude_message_ids=…, summarize_with_model_enabled=…) -> dict[str, Any] | None`

**Purpose:** Build one compression event payload for manual/auto UI-triggered compression.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _collect_recent_user_messages(chat, exclude_message_id) -> list[str]`

**Purpose:** Collect recent user messages.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _collect_direct_user_directives(chat, exclude_message_id) -> list[str]`

**Purpose:** Collect direct user directives.

#### `def _generate_history_summary_with_model(*, engine, model_name, prompt_messages, model_info_payload=…) -> str`

**Purpose:** Generate one non-streamed summary payload with the active model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_chat_history(chat, user_message_record, user_message, system_prompt, engine, model_name, model_info_payload, upload_manifests, sandbox_enabled) -> tuple[list[dict[str, Any]], dict[str, Any] | None]`

**Purpose:** Build LLM message history

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _split_generation_options(options, think_param_name, think_level_param_name) -> tuple[Any, Any, dict[str, Any]]`

**Purpose:** Split generation options

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _inject_ephemeral_system_notice(llm_messages, notice) -> None`

**Purpose:** Insert a one-off system notice after the main system prompt, without persisting a message.

#### `def _build_generate_kwargs(engine, model_name, llm_messages, think_value, think_level_value, clean_options, chat, selected_tool_servers, think_param_name, think_level_param_name, sync_operation_defaults) -> dict[str, Any]`

**Purpose:** Build generation kwargs

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _stream_chat_response(chat, engine, generate_kwargs, assistant_message_record, generation_id, compression_event, model_info_payload, system_prompt, current_user_message_id)`

**Purpose:** Stream and save assistant response

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Read or write Django ORM records.
5. Parse or serialize JSON payloads.

#### `def _path_is_within(path, root) -> bool`

**Purpose:** Message and chat management APIs.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _shared_file_allowed_roots() -> list[Path]`

**Purpose:** Shared file allowed roots.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _resolve_shared_file_path(raw_path) -> Path`

**Purpose:** Resolve shared file path.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def _resolve_uploaded_file_content_path(manifest) -> Path`

**Purpose:** Return the local path for one uploaded file manifest.

#### `def _range_not_satisfiable_response(file_size) -> HttpResponse`

**Purpose:** Range not satisfiable response.

**Steps:**

1. Return the computed result to the caller.
2. Build an HTTP response for the client.

#### `def _parse_single_byte_range(range_header, file_size) -> tuple[int, int] | None`

**Purpose:** Return one satisfiable byte range, including suffix ranges.

**Steps:**

1. Return the computed result to the caller.

#### `def _stream_local_file_response(request, target, *, mime_type, safe_name, disposition=…)`

**Purpose:** Stream a local file with HTTP Range support for media playback.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.
3. Build an HTTP response for the client.

#### `def _skills_error_response(exc) -> JsonResponse`

**Purpose:** Return a normalized JSON error for skills APIs.

**Steps:**

1. Return the computed result to the caller.
2. Build an HTTP response for the client.

#### `def _preset_mutation_response(payload) -> JsonResponse`

**Purpose:** Return a JSON response after invalidating model metadata.

#### `def _browser_portal_roots() -> list[Path]`

**Purpose:** Browser portal roots.

#### `def _browser_portal_debug_log_path(root) -> Path`

**Purpose:** Browser portal debug log path.

#### `def _browser_portal_debug_safe(value, *, depth=…) -> Any`

**Purpose:** Browser portal debug safe.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _browser_portal_http_event_body_for_log(data) -> dict[str, Any]`

**Purpose:** Compact portal POST body for debug.jsonl (typing floods the log otherwise).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _write_browser_portal_debug_event(root, event, **fields) -> None`

**Purpose:** Browser portal debug logging is intentionally disabled.

#### `def _read_browser_portal_state_from(root) -> dict[str, Any] | None`

**Purpose:** Return browser portal state from.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _is_active_browser_portal_state(payload) -> bool`

**Purpose:** Is active browser portal state.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _active_browser_portal_root() -> Path | None`

**Purpose:** Active browser portal root.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _browser_portal_state_path() -> Path`

**Purpose:** Browser portal state path.

**Steps:**

1. Return the computed result to the caller.

#### `def _browser_portal_events_dir() -> Path`

**Purpose:** Browser portal events dir.

**Steps:**

1. Return the computed result to the caller.

#### `def _read_browser_portal_state() -> dict[str, Any]`

**Purpose:** Return browser portal state.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [UI/_index](../../_index/)
