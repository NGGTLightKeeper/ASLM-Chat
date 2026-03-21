# mcp-browser-agent

MCP server for browser automation using Playwright's **accessibility tree** via CDP (Chrome DevTools Protocol). Instead of raw HTML or screenshots, the LLM receives a compact structured tree of interactive elements (~200–400 tokens), enabling precise and efficient web interaction without vision models or GPU.

---

## MCP Tools

### Navigation & State

| Tool | Description |
|------|-------------|
| `browser_navigate(url)` | Open a URL. Returns accessibility tree snapshot with element refs. |
| `browser_snapshot()` | Refresh the current page snapshot. Use to get updated element refs after interactions. |
| `browser_back()` | Go back to the previous page. |

### Interaction

| Tool | Description |
|------|-------------|
| `browser_click(ref)` | Click on an element by its ref ID (e.g. `"e5"`) |
| `browser_type(ref, text, clear_first=True, press_enter=False)` | Type text into an input field |
| `browser_scroll(direction="down", amount=500)` | Scroll the page up or down |
| `browser_press_key(key)` | Press a keyboard key (`Enter`, `Tab`, `Escape`, `ArrowDown`, etc.) |

### Content

| Tool | Description |
|------|-------------|
| `browser_read_page(max_chars=8000)` | Extract main text content of the current page (cleaned from nav, ads, scripts) |

---

## How It Works

The server uses CDP `Accessibility.getFullAXTree` to extract the full accessibility tree. Only semantically meaningful nodes (headings, links, buttons, inputs, etc.) are exposed to the LLM:

**Example snapshot output:**
```
## Current page
**URL:** https://example.com/search
**Title:** Search Results
**Elements:** 12 found

### Accessibility Tree
[e0] heading "Search Results"
[e1] link "First Result Title"
  [e2] link "Second Result Title"
[e3] textbox "Search" value="python"
[e4] button "Search"

### Interactive elements
- [e3] textbox "Search" value="python"
- [e4] button "Search"
- [e1] link "First Result Title"
```

The LLM then uses these `[eN]` refs with `browser_click`, `browser_type`, etc.

---

## Configuration

Hardcoded in `server.py`, adjustable at the top of the file:

| Constant | Default | Description |
|----------|---------|-------------|
| `BROWSER_WIDTH` | `1280` | Browser viewport width |
| `BROWSER_HEIGHT` | `800` | Browser viewport height |
| `MAX_A11Y_DEPTH` | `15` | Maximum accessibility tree traversal depth |
| `MAX_ELEMENTS` | `200` | Maximum elements per snapshot |
| `DOWNLOADS_DIR` | `../../_in/` | Directory for downloaded files |

The browser runs **non-headless** (visible window) for debugging. Change `headless=False` to `headless=True` in `ensure_open()` to run silently.

---

## Features

- **Auto-download handling** — downloaded files are automatically saved to `_in/`
- **Auto-dialog handling** — browser alerts/confirms/prompts are automatically accepted
- **Role-based clicking** — uses `get_by_role()` for reliable element targeting; falls back to `get_by_text()`
- **No vision model required** — works entirely with the accessibility API

---

## Installation

```bash
pip install mcp playwright
playwright install chromium
```

### MCP Configuration (mcp.json)

```json
{
  "browser-agent": {
    "command": "C:/Users/.../python.exe",
    "args": ["server.py"],
    "cwd": "C:/Users/.../mcp-browser-agent",
    "timeout": 4500000
  }
}
```

---

## Usage Examples

**Navigate and interact:**
```
1. browser_navigate("https://github.com")
   → Returns snapshot with element refs

2. browser_type("e3", "mcp python", press_enter=True)
   → Types in the search box and submits

3. browser_snapshot()
   → Refreshes view after page load

4. browser_click("e7")
   → Clicks a result link

5. browser_read_page()
   → Extracts the full article text
```

---

## Limitations

- One browser instance per MCP session (shared state across tool calls)
- Does not support multiple browser contexts or tabs simultaneously
- PDF, video, and heavy media pages are better handled by `mcp-web-search`'s `read_page`
