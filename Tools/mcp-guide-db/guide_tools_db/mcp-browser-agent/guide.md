# mcp-browser-agent

## What it is

`mcp-browser-agent` is an interactive browser automation tool using camoufox (stealth Firefox) with Playwright.
Pages are exposed as accessibility snapshots with short-lived element `ref` IDs.
No raw HTML, no CSS selectors, no vision model.

---

## Tools

### `browser_navigate(url)`

Open a URL. Returns a full snapshot (accessibility tree + interactive elements + page situation warnings).
Always call this first before any other browser tool.

### `browser_snapshot(scroll?, amount?)`

Refresh the page and return a full snapshot. Optionally scroll before snapshotting.
Call when: stale ref error, need full tree after compact actions, lazy-loaded content.

### `browser_click(ref | refs | key)`

Click an element by ref, batch-click multiple refs, or press a keyboard key.
Returns a compact snapshot (URL + interactive elements only).
If click navigates to a new page -- full snapshot is returned.

### `browser_type(ref, text, press_enter)`

Type text into an input field. Returns a compact snapshot.

### `browser_wait_for_user(message, timeout_seconds=45)`

Pause for user to manually interact (CAPTCHA, login, overlay).
Always navigate to a page first. Returns a fresh full snapshot after the wait.

### `browser_screenshot(full_page=false)`

Take a PNG screenshot. Use sandbox `read(path)` to inspect it visually.

---

## Output modes

- **Full snapshot** -- from `browser_navigate`, `browser_snapshot`, `browser_wait_for_user`. Includes accessibility tree, situation warnings, interactive elements.
- **Compact snapshot** -- from `browser_click`, `browser_type`. Includes URL + interactive elements only.

---

## Auto behaviors

- Cookie banners and overlays are auto-dismissed
- Page situations detected: CAPTCHA, login wall, HTTP errors, undismissable overlays
- Situation warnings appear in the snapshot header

---

## Golden rules

1. Always `browser_navigate` first -- nothing works without a page open.
2. Never invent refs -- only use refs from the latest snapshot.
3. Refs expire after every action -- each response has new refs.
4. On CAPTCHA -- use `browser_wait_for_user`, not `browser_click`.
5. On overlay warning -- try clicking close button, or `browser_wait_for_user`.
6. Going back -- use `browser_navigate(back_url)` from the snapshot.
7. Batch multiple clicks with `refs: [...]` instead of separate calls.

---

## State model

| Persists across calls | Does NOT persist |
| --- | --- |
| Browser session | Refs from older snapshots |
| Current page and URL | |
| Cookies and auth state | |
| Page history (Back URL) | |

---

## Common mistakes

| Mistake | Correct approach |
| --- | --- |
| Using refs from an outdated snapshot | Use only refs from the latest response |
| Inventing refs not in the snapshot | Only use refs that appeared in output |
| `browser_wait_for_user` before `browser_navigate` | Navigate first, then wait |
| `browser_click` on CAPTCHA | Use `browser_wait_for_user` |
| Thinking in CSS selectors | This tool is ref-based |
| Separate `browser_click` per checkbox | Use `refs: [...]` batch |
| Assuming screenshot was understood | Follow with sandbox `read()` |
