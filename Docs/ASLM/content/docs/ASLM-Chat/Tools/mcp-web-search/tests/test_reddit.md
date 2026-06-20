---
title: "test_reddit"
draft: false
---

## Module `test_reddit`

`Tools/mcp-web-search/tests/test_reddit.py` — ASLM Chat Python module.

---

## Overview

Reddit thread fetch: URL shaping, payload parsing, and the tiered fallback chain.

---

## Public functions

#### `def test_url_host_override() -> None`

**Purpose:** .json / page URLs honor a host override (so the old.reddit fallback hits the right host).

#### `def test_parse_payload_from_pre_wrapper() -> None`

**Purpose:** A listing rendered into a <pre> (Chrome's JSON viewer) parses like a raw body.

#### `def test_markdown_shape() -> None`

**Purpose:** Markdown carries the post header plus nested comments with author/score.

#### `def test_fallback_curl_blocked_then_browser_json(monkeypatch) -> None`

**Purpose:** curl 403 → browser .json (www) succeeds and is parsed into structured markdown.

#### `def test_fallback_old_reddit_json(monkeypatch) -> None`

**Purpose:** curl 403 + www browser block → old.reddit .json is the next rung and wins.

---

## Related

- [tests/_index](../_index/)
