---
title: "github"
draft: false
---

## Module `github`

`Tools/mcp-web-search/custom_domains/github.py` — ASLM Chat Python module.

---

## Public functions

#### `def is_github_url(url) -> bool`

**Purpose:** True when URL targets github.com.

#### `async def fetch_github_page(url, timeout) -> str`

**Purpose:** Fetch repo, issue, blob, or tree via GitHub API and return formatted markdown.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

---

## Private functions

#### `def _host(url) -> str`

**Purpose:** Normalize URL host (strip www./m. prefixes).

#### `def _repo_parts(url) -> tuple[str, str, list[str]] | None`

**Purpose:** Parse owner, repo, and remaining path segments from a GitHub URL.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _github_headers() -> dict[str, str]`

**Purpose:** Build GitHub REST API headers, optionally with GITHUB_TOKEN / GH_TOKEN.

**Steps:**

1. Return the computed result to the caller.

#### `def _api_get_json(url, timeout) -> Any`

**Purpose:** Synchronous GET returning parsed JSON from the GitHub API.

**Steps:**

1. Return the computed result to the caller.

#### `def _decode_content_payload(data) -> str`

**Purpose:** Decode base64 contents field from a GitHub contents API response.

**Steps:**

1. Return the computed result to the caller.

#### `def _format_repo(repo, readme, url) -> str`

**Purpose:** Format repository metadata and README as markdown.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _format_issue(issue, comments, url) -> str`

**Purpose:** Format issue metadata, body, and comments as markdown.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _format_tree(items, owner, repo, ref, path, url) -> str`

**Purpose:** Format directory listing from GitHub contents/tree API as markdown.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [custom_domains/_index](../../../_index/)
