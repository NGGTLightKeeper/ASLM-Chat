# Copyright NEXTGGTECH. Elastic License 2.0.

from pathlib import Path
import os

# Base paths
BROWSER_AGENT_ROOT = Path(__file__).resolve().parent
SANDBOX_DIR = BROWSER_AGENT_ROOT.parent / "mcp-sandbox" / "_sandbox"
DOWNLOADS_DIR = Path(os.getenv("ASLM_BROWSER_WORKSPACE_DIR", SANDBOX_DIR)).resolve()

# Browser window settings
BROWSER_WIDTH = 1280
BROWSER_HEIGHT = 800
BROWSER_HEADLESS = os.getenv("ASLM_BROWSER_HEADLESS", "0").strip().lower() not in {"0", "false", "no", "off"}

# Accessibility snapshot limits
MAX_A11Y_DEPTH = 15
MAX_ELEMENTS = 200
MAX_MAIN_INTERACTIVE = 60
MAX_OTHER_INTERACTIVE = 10

# Snapshot text preview
AUTO_TEXT_PREVIEW_LEN = 1500

# Readability.js fallback settings
READABILITY_JS_CDN = "https://cdn.jsdelivr.net/npm/@mozilla/readability@0.5.0/Readability.min.js"
READABILITY_MIN_LENGTH = 200
