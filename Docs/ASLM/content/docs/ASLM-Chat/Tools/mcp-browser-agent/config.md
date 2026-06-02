---
title: "config"
draft: false
---

## Module `config`

`Tools/mcp-browser-agent/config.py` — see source for implementation details.

---

## Module constants

#### `BROWSER_AGENT_ROOT`

**Purpose:** Module constant `BROWSER_AGENT_ROOT` (Path(__file__).resolve().parent…).

#### `SANDBOX_DIR`

**Purpose:** Module constant `SANDBOX_DIR` (BROWSER_AGENT_ROOT.parent / 'mcp-sandbox' / '_sandbox'…).

#### `DOWNLOADS_DIR`

**Purpose:** Module constant `DOWNLOADS_DIR` (Path(os.getenv('ASLM_BROWSER_WORKSPACE_DIR', SANDBOX_DIR)).resolve()…).

#### `BROWSER_WIDTH`

**Purpose:** Module constant `BROWSER_WIDTH` (1280…).

#### `BROWSER_HEIGHT`

**Purpose:** Module constant `BROWSER_HEIGHT` (800…).

#### `BROWSER_HEADLESS`

**Purpose:** Module constant `BROWSER_HEADLESS` (os.getenv('ASLM_BROWSER_HEADLESS', '0').strip().lower() not in {'0', 'false', 'n…).

#### `MAX_A11Y_DEPTH`

**Purpose:** Module constant `MAX_A11Y_DEPTH` (15…).

#### `MAX_ELEMENTS`

**Purpose:** Module constant `MAX_ELEMENTS` (200…).

#### `MAX_MAIN_INTERACTIVE`

**Purpose:** Module constant `MAX_MAIN_INTERACTIVE` (60…).

#### `MAX_OTHER_INTERACTIVE`

**Purpose:** Module constant `MAX_OTHER_INTERACTIVE` (10…).

#### `AUTO_TEXT_PREVIEW_LEN`

**Purpose:** Module constant `AUTO_TEXT_PREVIEW_LEN` (1500…).

#### `READABILITY_JS_CDN`

**Purpose:** https://cdn.jsdelivr.net/npm/@mozilla/readability@0.5.0/Readability.min.js

#### `READABILITY_MIN_LENGTH`

**Purpose:** Module constant `READABILITY_MIN_LENGTH` (200…).

---

## Related

- [mcp-browser-agent/_index](_index/)
