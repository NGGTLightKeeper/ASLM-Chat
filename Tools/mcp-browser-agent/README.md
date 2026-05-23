# mcp-browser-agent

Browser automation tool server for ASLM. The model orients through a compact
controls snapshot, then acts on element refs such as `e8`.

The browser runs headless by default so the user sees the chat portal instead
of a separate desktop window. Set `ASLM_BROWSER_HEADLESS=0` before starting the
app/server to show the real Camoufox window for debugging.

## Tools

### Orientation

| Tool | Description |
| --- | --- |
| `browser_navigate(url)` | Open a URL and return a compact controls-only snapshot. |
| `browser_snapshot(full?)` | Refresh the snapshot without changing page state. Use `full=true` for page text and the raw accessibility tree. |

### Actions

| Tool | Description |
| --- | --- |
| `browser_click(ref)` | Click one element by ref. |
| `browser_key(key)` | Press one keyboard key or shortcut on the current page/focused element. Do not use for text entry. |
| `browser_scroll(direction, amount?)` | Scroll the page viewport up or down. |
| `browser_text(action?, ref?, text?, ...)` | Read, set, replace, or delete text in an input/editor. If `text` is provided without `action`, it sets the field text. |
| `browser_wait_for_user(message, timeout_seconds?)` | Pause while the user handles login, CAPTCHA, 2FA, or another manual blocker. |
| `browser_screenshot(full_page?)` | Capture a PNG screenshot. Vision models receive inline preview; non-vision models receive metadata and file paths. |

## Text Editing

Use `browser_text` for all text entry and editing:

```json
{"action": "set", "ref": "e8", "text": "hello"}
```

```json
{"action": "replace", "ref": "e8", "old_text": "hello", "new_text": "hello world"}
```

```json
{"action": "replace", "ref": "e8", "range": "2:2", "text": "updated second line"}
```

```json
{"action": "delete", "ref": "e8", "range": "3:3"}
```

## Current Orientation Contract

Snapshots are model-facing text with a small parsed JSON header plus grouped
controls.

- URL and title
- fresh-ref rule
- page situation warnings when detected
- parsed counts (`text_inputs`, `buttons`, `links`)
- grouped text inputs, buttons/controls, links, and other controls

Default snapshots intentionally hide page text and the raw accessibility tree.
Use `browser_snapshot(full=true)` when the model needs page content, footer/nav
content, or the low-level tree.

Refs are refreshed on every snapshot and are only valid for the latest observed
page state.

## Verification

Run the local deterministic smoke test:

```bash
python scripts/smoke_browser_agent.py
```

It checks default/full snapshots, click/search overlay, text set/read/replace/delete,
contenteditable, CodeMirror, Ace, scroll, and screenshot metadata.

Run the local Ollama screenshot vision probe:

```bash
python scripts/probe_ollama_browser_screenshot.py --model gemma4:31b-cloud
```

It captures a browser screenshot, verifies inline base64 output, sends it to the
local Ollama `/api/chat` endpoint, and checks that the vision model can read the
visible token.

## Known Cleanup Still Pending

- Add first-class UI rendering for browser state.
