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

#### `async def fetch_with_camoufox(url: str, *, wait_sec: float = 4.0, headless: bool = True, humanize: bool = True, geoip: bool = False, locale: str = "en-US", proxy: Optional[dict] = None, warmup_urls: Optional[list[str]] = None, warmup_count: int = 1, timeout_sec: float = 45.0, process_timeout: float = 0.0, normalize: bool = True) -> FetchResult`

**Purpose:** Fetch url in an isolated Camoufox subprocess; returns FetchResult.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Parse or serialize JSON payloads.
6. Spawn or communicate with a child process.

#### `async def fetch_batch_with_camoufox(urls: list[str], *, max_concurrency: int = 2, timeout_sec: float = 45.0, process_timeout: float = 0.0, wait_sec: float = 4.0, headless: bool = True, humanize: bool = True, geoip: bool = False, locale: str = "en-US", proxy: Optional[dict] = None, warmup_urls: Optional[list[str]] = None, warmup_count: int = 1, normalize: bool = True) -> list[FetchResult]`

**Purpose:** Fetch multiple URLs with limited concurrency (keep max_concurrency at 1–2).

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

#### `async def fetch_page_json_with_camoufox(page_url: str, *, json_query: str = "limit=50&depth=3", wait_sec: float = 4.0, headless: bool = True, humanize: bool = True, geoip: bool = False, locale: str = "en-US", proxy: Optional[dict] = None, warmup_urls: Optional[list[str]] = None, warmup_count: int = 0, timeout_sec: float = 45.0, process_timeout: float = 0.0) -> FetchResult`

**Purpose:** Open thread HTML in Camoufox, then fetch .json in-page with session cookies.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Parse or serialize JSON payloads.
6. Spawn or communicate with a child process.

---

## Private functions

#### `def _kill_process_tree(pid: int) -> None`

**Purpose:** Kill a process and its children (Firefox spawned by Camoufox).

**Steps:**

1. Handle errors and map them to a safe response.
2. Spawn or communicate with a child process.

#### `async def _run_camoufox_worker(url: str, payload: dict[str, object], *, process_timeout: float) -> FetchResult`

**Purpose:** Run the Camoufox worker subprocess with an arbitrary JSON payload.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Parse or serialize JSON payloads.
6. Spawn or communicate with a child process.

---

## Related

- [fetch/_index](../../../../_index/)
