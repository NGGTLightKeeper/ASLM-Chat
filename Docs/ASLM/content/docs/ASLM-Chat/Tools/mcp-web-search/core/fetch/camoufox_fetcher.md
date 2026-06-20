---
title: "camoufox_fetcher"
draft: false
---

## Module `camoufox_fetcher`

`Tools/mcp-web-search/core/fetch/camoufox_fetcher.py` — ASLM Chat Python module.

---

## Classes

### `class FetchResult`

**Purpose:** Type `FetchResult` defined in `camoufox_fetcher.py`.

---

## Public functions

#### `async def fetch_page_json_with_camoufox(page_url, *, json_query=…, wait_sec=…, headless=…, humanize=…, geoip=…, locale=…, proxy=…, warmup_urls=…, warmup_count=…, timeout_sec=…, process_timeout=…) -> FetchResult`

**Purpose:** Open thread HTML in Camoufox, then fetch .json in-page with session cookies.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

#### `def is_camoufox_available() -> bool`

**Purpose:** Return True if the camoufox package and its browser binary exist.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `async def fetch_with_camoufox(url, *, wait_sec=…, headless=…, humanize=…, geoip=…, locale=…, proxy=…, warmup_urls=…, warmup_count=…, timeout_sec=…, process_timeout=…, normalize=…) -> FetchResult`

**Purpose:** Fetch url in an isolated Camoufox subprocess; returns FetchResult.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Parse or serialize JSON payloads.
6. Spawn or communicate with a child process.

#### `async def fetch_batch_with_camoufox(urls, *, max_concurrency=…, timeout_sec=…, process_timeout=…, wait_sec=…, headless=…, humanize=…, geoip=…, locale=…, proxy=…, warmup_urls=…, warmup_count=…, normalize=…) -> list[FetchResult]`

**Purpose:** Fetch multiple URLs with limited concurrency (keep max_concurrency at 1–2).

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

---

## Private functions

#### `async def _run_camoufox_worker(url, payload, *, process_timeout) -> FetchResult`

**Purpose:** Run the Camoufox worker subprocess with an arbitrary JSON payload.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Parse or serialize JSON payloads.
5. Spawn or communicate with a child process.

#### `def _kill_process_tree(pid) -> None`

**Purpose:** Kill a process and its children (Firefox spawned by Camoufox).

**Steps:**

1. Handle errors and map them to a safe response.
2. Spawn or communicate with a child process.

---

## Related

- [fetch/_index](../../../../_index/)
