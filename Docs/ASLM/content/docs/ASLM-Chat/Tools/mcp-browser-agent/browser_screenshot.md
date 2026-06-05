---
title: "browser_screenshot"
draft: false
---

## Module `browser_screenshot`

`Tools/mcp-browser-agent/browser_screenshot.py` — ASLM Chat Python module.

---

## Public functions

#### `async def capture_browser_screenshot(full_page, context) -> dict[str, Any]`

**Purpose:** Capture a PNG screenshot and return structured image metadata for the model.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

---

## Private functions

#### `def _load_model_runtime_metadata(module_dir) -> dict[str, Any]`

**Purpose:** Load model runtime metadata from the module dir or the default tools path.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _model_supports_vision(context) -> tuple[bool, dict[str, Any], str]`

**Purpose:** Return whether the active model supports vision according to runtime metadata.

**Steps:**

1. Return the computed result to the caller.

#### `def _png_dimensions(data) -> dict[str, int] | None`

**Purpose:** Parse width and height from a PNG file header.

**Steps:**

1. Return the computed result to the caller.

#### `def _sandbox_screens_dir(context) -> tuple[Path | None, str]`

**Purpose:** Resolve the sandbox screenshots directory when sandbox mode is active.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _image_result_from_png(*, data, path, host_path, supports_vision, model_record, metadata_source) -> dict[str, Any]`

**Purpose:** Build the image payload dict with optional inline preview for vision models.

**Steps:**

1. Return the computed result to the caller.

#### `def _structured_image_result(image, *, supports_vision) -> dict[str, Any]`

**Purpose:** Wrap a captured image into the tool result shape expected by MCP callers.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [mcp-browser-agent/_index](../../_index/)
