# mcp-browser-agent

## Overview

`mcp-browser-agent` is an MCP server for interactive browser automation using **camoufox** — a stealth Firefox build — with Playwright's `aria_snapshot()` for structured page understanding.

The model interacts with pages through an **accessibility tree**: compact semantic roles, names, and short-lived `ref` IDs like `e0`, `e3`, `e12`. No raw HTML, no CSS selectors, no vision model required.

**Output modes:**

- **Full snapshot** — returned by `browser_navigate`, `browser_snapshot`, `browser_wait_for_user`. Includes accessibility tree, page situation warnings, interactive elements list.
- **Compact snapshot** — returned by `browser_click`, `browser_type`. Includes URL + interactive elements only. If a click navigates to a new page, a full snapshot is returned automatically.

Automatic behaviors on every **full** snapshot:

- **Cookie banners and overlays** are auto-dismissed (known selectors + JS heuristic + Escape key)
- **Page situation warnings** are injected: CAPTCHA, login wall, HTTP error pages, undismissable overlays

---

## Core Mental Model

> A stateful browser session where pages are exposed as accessibility-based interactive elements, and actions are performed through element references from the latest snapshot.

The model works with:

- Current page URL and title
- Accessibility snapshot with semantic roles and names (full snapshots only)
- Interactive elements tagged with `ref` IDs (e.g. `[e3] button "Login"`)
- Situation warnings embedded in the snapshot header

**Key principles:**

1. The working unit is the `ref` from the **latest** snapshot — not a DOM selector
2. The accessibility tree may not contain all text content on JS-heavy (SPA) pages — use `browser_screenshot()` + sandbox `read()` for visual inspection when text extraction is insufficient
3. Refs expire after every action — always use refs from the most recent snapshot

---

## Available Tools

### `browser_navigate(url)`

Open a URL and return a **full snapshot**.

After navigation the server waits for DOM load + 2.5 s render pause. `networkidle` is intentionally skipped to avoid hanging on SPA sites.

```json
{ "tool": "browser_navigate", "url": "https://example.com/login" }
```

**Going back:** every full snapshot shows `**Back URL:**` — call `browser_navigate(back_url)` to return to the previous page.

---

### `browser_snapshot(scroll?, amount?)`

Refresh the current page and return a **full snapshot** with updated refs. Optionally scrolls before snapshotting.

| Argument | Description | Default |
| --- | --- | --- |
| `scroll` | `"up"` or `"down"` — scroll before snapshotting | — |
| `amount` | Pixels to scroll | `500` |

Call when:

- stale ref error — `"Could not locate element ref=..."`
- you need the full accessibility tree after a series of compact-snapshot actions
- after dynamic content loads (popups, lazy-load, animations)
- to scroll and reveal more content in one step

```json
{ "tool": "browser_snapshot", "scroll": "down", "amount": 800 }
```

---

### `browser_click(ref | refs | key)`

Click an interactive element by ref, click multiple refs sequentially, or press a keyboard key. Returns a **compact snapshot**.

If the click navigates to a new page, a **full snapshot** is returned automatically.

**Click strategy (tried in order):**

1. Standard `.click()` — works for most visible elements
2. `.check(force=True)` — for radio/checkbox; handles hidden `<input>` with visible `<label>` overlay
3. `.click(force=True)` — bypasses visibility and pointer-events checks
4. JavaScript `el.click()` — fires native click event directly as a last resort

```json
{ "tool": "browser_click", "ref": "e3" }
{ "tool": "browser_click", "refs": ["e5", "e8", "e12"] }
{ "tool": "browser_click", "key": "Enter" }
```

**Batching multiple clicks:** use `{"refs": [...]}` to click several checkboxes or options from the same snapshot in one call. For keyboard actions (submit, dismiss, navigate) use `{"key": "..."}` instead of a separate tool.

---

### `browser_type(ref, text, press_enter)`

Type text into an input field.

| Argument | Description | Default |
| --- | --- | --- |
| `ref` | Element reference | — |
| `text` | Text to type | — |
| `press_enter` | Press Enter after typing | `false` |

```json
{ "tool": "browser_type", "ref": "e7", "text": "machine learning", "press_enter": true }
```

---

### `browser_wait_for_user(message, timeout_seconds)`

Pause and wait for the user to manually interact with the browser.

| Argument | Description | Default |
| --- | --- | --- |
| `message` | What the user needs to do | — |
| `timeout_seconds` | Seconds to wait before resuming | `45` |

**When to call:**

- CAPTCHA detected (reCAPTCHA, hCaptcha, Cloudflare, Turnstile)
- Login form requires credentials
- Age gate or manual verification required
- Overlay that auto-dismiss could not close — snapshot shows `⚠️ OVERLAY`

**Important:**

- Always call `browser_navigate(url)` **before** `browser_wait_for_user` — no page open = no result
- Write a clear `message` describing exactly what the user must do
- After the wait, a fresh **full snapshot** is returned — check it before continuing

```json
{ "tool": "browser_wait_for_user", "message": "Please solve the CAPTCHA", "timeout_seconds": 45 }
```

---

### `browser_screenshot(full_page)`

Take a PNG screenshot of the current page and save it to `_in/`.

| Argument | Description | Default |
| --- | --- | --- |
| `full_page` | Capture full scrollable page | `false` |

Returns the file path and a sandbox `read()` hint. Use `read(path)` in the sandbox to visually inspect the screenshot.

**When to use:**

- Accessibility tree is missing significant text (canvas, iframe, CSS-hidden content)
- You need to visually verify page layout or content

**Workflow:**

```text
1. browser_screenshot()
   → returns: "Screenshot saved: ...\nCall read('...') to inspect visually."
2. read('_in/screenshot_<ts>.png')   ← run in sandbox to see it
```

```json
{ "tool": "browser_screenshot", "full_page": false }
```

---

## Overlay and Blocking Detection

Every **full snapshot** runs overlay handling:

1. **Auto-dismiss** — tries to close cookie banners, consent dialogs, registration walls, and promo popups using known selectors, JS heuristics, and Escape key
2. **Warning** — if a large fixed overlay still covers the viewport center after dismissal, snapshot includes `⚠️ OVERLAY: ...` in `### Page Situation`. **All tools remain usable.**
3. **Recovery** — try `browser_click` on a visible close button, or call `browser_wait_for_user` so the user closes it manually

Situations detected:

- CAPTCHA (reCAPTCHA / hCaptcha / Cloudflare / Turnstile)
- Login wall (visible password input)
- HTTP error pages (404 / 403 / 500)

---

## Operational Workflow

```text
1. browser_navigate(url)                         ← always first
2. Read snapshot — check URL, title, Page Situation warnings
3. If ⚠️ CAPTCHA → browser_wait_for_user(...)
4. If ⚠️ OVERLAY → try browser_click on close button, or browser_wait_for_user
5. Identify refs from snapshot → browser_click(ref) or browser_type(ref, ...)
6. Each action returns a compact snapshot with new refs — use them immediately
7. If you need the full tree or more content → browser_snapshot(scroll="down")
8. If text is missing from tree → browser_screenshot() → read(path)
```

---

## Critical Rules

1. **Always `browser_navigate` first** — `browser_wait_for_user`, screenshots, and snapshots only work after a URL is open
2. **Never invent refs** — only use refs that appeared in the latest snapshot
3. **Refs expire after every action** — click, type, navigate all return a new snapshot with new refs
4. **On `⚠️ OVERLAY`** — tools still work; try to close it or call `browser_wait_for_user`
5. **On `⚠️ CAPTCHA`** — call `browser_wait_for_user`, not `browser_click`
6. **Going back** — call `browser_navigate(back_url)` using the Back URL from the snapshot

---

## Tool Selection Guide

| Goal | Tool |
| --- | --- |
| Open a URL | `browser_navigate` |
| Go back to previous page | `browser_navigate(back_url)` from snapshot |
| Refresh full tree / stale ref error | `browser_snapshot` |
| Scroll and refresh in one step | `browser_snapshot(scroll="down")` |
| Click a button, link, checkbox, radio | `browser_click(ref)` |
| Click multiple elements at once | `browser_click(refs=[...])` |
| Submit / keyboard navigation / dismiss | `browser_click(key="Enter")` |
| Fill a form field | `browser_type` |
| CAPTCHA / login / overlay block | `browser_wait_for_user` |
| Visual inspection / canvas / iframe | `browser_screenshot` → `read` |

---

## State Model

| Persists across calls | Does NOT persist |
| --- | --- |
| Browser session | Refs from older snapshots |
| Current page and URL | |
| Cookies and auth state | |
| Page history (Back URL) | |

---

## Common Mistakes

| # | Mistake |
| --- | --- |
| 1 | Using refs from an outdated snapshot |
| 2 | Inventing refs that were never in the snapshot |
| 3 | Calling `browser_wait_for_user` before `browser_navigate` — no page is open yet |
| 4 | Calling `browser_click` on a CAPTCHA — use `browser_wait_for_user` |
| 5 | Thinking in CSS selectors — this tool is ref-based, not selector-based |
| 6 | Using separate `browser_click` calls for each checkbox — use `refs: [...]` batch instead |
| 7 | Assuming a screenshot was understood visually — always follow with sandbox `read()` |

---

## Failure Recovery

### Stale ref / element not found

```text
1. browser_snapshot()              ← get fresh refs
2. browser_snapshot(scroll="down") if element might be off-screen
3. Retry with current ref
```

### Click does nothing / button stays disabled

```text
1. Check if a required step was skipped (e.g. select an answer before submitting)
2. browser_snapshot() → interact with the correct element
```

### Page text is missing from accessibility tree

```text
1. browser_screenshot()
2. read(path)                      ← run in sandbox
```

### Overlay won't go away

```text
browser_wait_for_user("Please close the popup manually")
```

---

## Summary

| Field | Value |
| --- | --- |
| **Tool name** | `mcp-browser-agent` |
| **Category** | Interactive web UI automation |
| **Browser** | Camoufox (Firefox stealth) via Playwright |
| **Primary abstraction** | Accessibility snapshot + short-lived element refs |
| **Auto behaviors** | Cookie/overlay dismiss, overlay warning, situation detection |
| **Click strategy** | Standard → check(force) → force → JS eval |
| **State** | Stateful session; refs are snapshot-scoped |
| **Best use cases** | Browser navigation, form filling, quizzes, dynamic web apps |
| **Poor fit for** | Raw HTML scraping, selector-based automation, large-scale crawling |
