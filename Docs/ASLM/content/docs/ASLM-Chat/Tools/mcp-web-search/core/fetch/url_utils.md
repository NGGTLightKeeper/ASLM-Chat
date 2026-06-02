---
title: "url_utils"
draft: false
---

## Module `url_utils`

`Tools/mcp-web-search/core/fetch/url_utils.py` — ASLM Chat Python module.

---

## Classes

### `class UnsafeFetchUrl`

**Purpose:** Type `UnsafeFetchUrl` defined in `url_utils.py`.

---

## Public functions

#### `def normalize_url(url) -> str`

**Purpose:** Strip tracking query params and normalize scheme, host, and path.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def has_non_text_extension(url) -> bool`

**Purpose:** Return True when URL path points to a non-text binary/media asset.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def is_non_text_content_type(content_type) -> bool`

**Purpose:** Return True for content types that should not enter text extraction.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def validate_public_fetch_url(url, *, allow_private=…) -> str`

**Purpose:** Validate a URL before an LLM-controlled web fetch (public HTTP/S only by default).

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def validate_redirect_target(current_url, location, *, allow_private=…) -> str`

**Purpose:** Resolve and validate one redirect Location header.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def max_safe_redirects() -> int`

**Purpose:** Maximum redirect hops allowed per fetch.

---

## Private functions

#### `def _private_fetch_allowed() -> bool`

**Purpose:** True when ASLM_WEB_ALLOW_PRIVATE_NET permits RFC1918 / link-local targets.

**Steps:**

1. Return the computed result to the caller.

#### `def _host_is_ip_literal(host) -> bool`

**Purpose:** True when host is a literal IP address (v4 or v6).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _is_blocked_ip(ip_text) -> bool`

**Purpose:** True when IP is not globally routable (private, loopback, link-local, etc.).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _resolve_host_ips(host) -> set[str]`

**Purpose:** Resolve host to A/AAAA addresses for SSRF checks.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

---

## Related

- [fetch/_index](../../../../_index/)
