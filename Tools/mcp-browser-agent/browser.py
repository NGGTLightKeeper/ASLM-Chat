# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import concurrent.futures
import importlib.util
import logging
import re
import sys
import threading
from pathlib import Path
from typing import Any

from camoufox.async_api import AsyncCamoufox
from mcp.types import TextContent
from playwright.async_api import BrowserContext, Page

SERVER_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = SERVER_ROOT / "config.py"


def _load_local_config():
    """Load the sibling config module without relying on global sys.path order."""

    spec = importlib.util.spec_from_file_location("mcp_browser_agent_config", CONFIG_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load browser-agent config from {CONFIG_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_config = _load_local_config()

AUTO_TEXT_PREVIEW_LEN = _config.AUTO_TEXT_PREVIEW_LEN
BROWSER_HEIGHT = _config.BROWSER_HEIGHT
BROWSER_WIDTH = _config.BROWSER_WIDTH
DOWNLOADS_DIR = _config.DOWNLOADS_DIR
MAX_A11Y_DEPTH = _config.MAX_A11Y_DEPTH
MAX_ELEMENTS = _config.MAX_ELEMENTS
MAX_MAIN_INTERACTIVE = _config.MAX_MAIN_INTERACTIVE


class BrowserRuntime:
    """Keep one dedicated event loop alive for all browser operations."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        loop.run_forever()

    def ensure_started(self) -> None:
        if self._thread is not None and self._thread.is_alive() and self._loop is not None:
            return

        with self._lock:
            if self._thread is not None and self._thread.is_alive() and self._loop is not None:
                return

            self._ready.clear()
            self._thread = threading.Thread(
                target=self._thread_main,
                name="mcp-browser-agent-loop",
                daemon=True,
            )
            self._thread.start()
            self._ready.wait()

    def submit(self, coro) -> concurrent.futures.Future:
        self.ensure_started()
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop)


_browser_runtime = BrowserRuntime()


async def run_in_browser_loop(
    coro,
    session=None,
    interval: float = 3.0,
    message: str = "working...",
):
    """Run a browser coroutine on the dedicated browser loop."""

    future = _browser_runtime.submit(coro)
    wrapped = asyncio.wrap_future(future)

    try:
        while True:
            done, _pending = await asyncio.wait({wrapped}, timeout=interval)
            if wrapped in done:
                return wrapped.result()

            if session is not None:
                try:
                    await session.send_log_message(level="debug", data=message, logger="browser-agent")
                except Exception:
                    pass
    except asyncio.CancelledError:
        future.cancel()
        raise

if sys.platform.startswith("win"):
    # Playwright/Camoufox may leave subprocess transports pending on shutdown.
    # Guard their destructors so tool calls do not emit false crash traces.
    try:
        import asyncio.base_subprocess as _base_subprocess
        import asyncio.proactor_events as _proactor_events

        _orig_pipe_del = _proactor_events._ProactorBasePipeTransport.__del__
        _orig_subproc_del = _base_subprocess.BaseSubprocessTransport.__del__

        def _safe_pipe_del(self):
            try:
                _orig_pipe_del(self)
            except Exception:
                pass

        def _safe_subproc_del(self):
            try:
                _orig_subproc_del(self)
            except Exception:
                pass

        _proactor_events._ProactorBasePipeTransport.__del__ = _safe_pipe_del
        _base_subprocess.BaseSubprocessTransport.__del__ = _safe_subproc_del
    except Exception:
        pass


# Logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("browser-agent")


# Accessibility tree constants
INTERACTIVE_ROLES = {
    "button",
    "link",
    "textbox",
    "searchbox",
    "combobox",
    "checkbox",
    "radio",
    "switch",
    "tab",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "option",
    "slider",
    "spinbutton", "treeitem",
}

SEMANTIC_ROLES = INTERACTIVE_ROLES | {
    "heading",
    "img",
    "navigation",
    "main",
    "banner",
    "contentinfo",
    "complementary",
    "form",
    "region",
    "list",
    "listitem",
    "table",
    "row",
    "cell",
    "dialog",
    "alert",
    "status",
    "progressbar",
    "separator",
    "toolbar",
}


# Landmark tracking
LANDMARK_ROLES = {
    "banner",
    "main",
    "contentinfo",
    "navigation",
    "complementary",
    "form",
    "region",
}

SKIP_ROLES = {
    "none",
    "presentation",
    "generic",
    "paragraph",
    "text",
    "strong",
    "emphasis",
    "code",
}


# Noise filters
_NOISE_NAME_PATTERNS = re.compile(
    r"^(User avatar|icon|Скопировать код|Показать полностью|"
    r"Показать обсуждения|Самые популярные|Оставить комментарий|"
    r"принципы сообщества|отдельный форум|Посмотреть \d+ отв|"
    r"Ответить|Не нравится|VKontakte|Telegram|Get it on|Skolkovo|cc-wiki|"
    r"использования|конфиденциальности|Тарифы|Прессе|Команда|Помощь|"
    r"О нас|Контакты|Каталог)$",
    re.IGNORECASE,
)

_COMMENT_BUTTON_RE = re.compile(r"^\d+$")


# Snapshot parsing patterns
_LINE_RE = re.compile(
    r'^(?P<indent>\s*)'
    r'- (?P<role>[A-Za-z][A-Za-z0-9_-]*)'
    r'(?::(?=\s*$))?'
    r'(?:\s+"(?P<name>[^"]*)")?'
    r'(?P<attrs>.*)?$'
)
_ATTR_RE = re.compile(r'\[(?P<key>\w+)(?:=(?P<val>[^\]]+))?\]')


# Accessibility tree extraction

# Build a compact accessibility tree with stable element refs
async def get_accessibility_tree(page: Page) -> tuple[list[dict], str]:
    """Extract the current accessibility tree and assign stable refs."""

    try:
        yaml_text = await page.locator("body").aria_snapshot(timeout=10000)
    except Exception as exc:
        log.warning(f"aria_snapshot failed: {exc}")
        return [], "(accessibility tree unavailable)"

    elements: list[dict] = []
    lines: list[str] = []
    ref_counter = 0

    # Keep the active landmark in sync with snapshot indentation.
    landmark_stack: list[tuple[int, str]] = []
    current_landmark = "unknown"

    # Walk the YAML-like aria snapshot line by line.
    for raw_line in yaml_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or not stripped.startswith("-"):
            continue

        match = _LINE_RE.match(raw_line)
        if not match:
            continue

        indent_str = match.group("indent") or ""
        depth = len(indent_str) // 2
        role = (match.group("role") or "").strip().rstrip(":")
        name = match.group("name") or ""
        attrs_str = match.group("attrs") or ""

        if depth > MAX_A11Y_DEPTH or ref_counter >= MAX_ELEMENTS:
            continue

        if role in SKIP_ROLES and not name:
            continue

        is_interactive = role in INTERACTIVE_ROLES
        is_semantic = role in SEMANTIC_ROLES

        if not (is_semantic or name):
            continue

        # Drop landmarks that are no longer active at the current depth.
        while landmark_stack and landmark_stack[-1][0] >= depth:
            landmark_stack.pop()

        if role in LANDMARK_ROLES:
            landmark_stack.append((depth, role))
            current_landmark = role
        elif landmark_stack:
            current_landmark = landmark_stack[-1][1]
        else:
            current_landmark = "unknown"

        # Convert bracket attributes into plain Python values.
        attrs: dict[str, Any] = {}
        for attr_match in _ATTR_RE.finditer(attrs_str):
            key = attr_match.group("key")
            val = attr_match.group("val")
            if val is None:
                attrs[key] = True
            else:
                val = val.strip('"\'')
                if val == "true":
                    attrs[key] = True
                elif val == "false":
                    attrs[key] = False
                else:
                    try:
                        attrs[key] = int(val)
                    except ValueError:
                        attrs[key] = val

        ref = f"e{ref_counter}"
        ref_counter += 1

        elem: dict[str, Any] = {
            "ref": ref, "role": role, "name": name,
            "landmark": current_landmark, "depth": depth,
        }
        if is_interactive:
            elem["interactive"] = True
        if "value" in attrs:
            elem["value"] = str(attrs["value"])
        if "level" in attrs:
            elem["level"] = attrs["level"]
        if "checked" in attrs:
            elem["checked"] = attrs["checked"]
        if "expanded" in attrs:
            elem["expanded"] = attrs["expanded"]
        if attrs.get("disabled"):
            elem["disabled"] = True
        if attrs.get("required"):
            elem["required"] = True

        elements.append(elem)

        # Keep the readable tree focused on content-bearing regions.
        show_in_tree = current_landmark in ("main", "dialog", "form", "region", "unknown", "complementary")

        if show_in_tree:
            indent = "  " * depth
            label_parts = [f"[{ref}]", role]
            if name:
                label_parts.append(f'"{name}"')
            if elem.get("value"):
                label_parts.append(f'value="{elem["value"]}"')
            if elem.get("level"):
                label_parts.append(f'level={elem["level"]}')
            if elem.get("checked") is not None:
                label_parts.append(f'checked={elem["checked"]}')
            if elem.get("disabled"):
                label_parts.append("(disabled)")
            lines.append(f"{indent}{' '.join(label_parts)}")

    tree_text = "\n".join(lines)
    return elements, tree_text


# Accessibility tree filtering

# Hide low-value elements from model-facing output
def _is_noise_element(elem: dict) -> bool:
    """Return whether an element should be hidden from tool output."""

    name = elem.get("name", "")
    role = elem.get("role", "")
    landmark = elem.get("landmark", "")

    # Keep content-region controls visible even if they look generic.
    if landmark in ("main", "dialog", "form"):
        return False

    if not name and role in ("link", "button", "img"):
        return True

    if name and _NOISE_NAME_PATTERNS.match(name):
        return True

    if role == "button" and _COMMENT_BUTTON_RE.match(name) and landmark != "main":
        return True

    if "avatar" in name.lower() or "User avatar" in name:
        return True

    return False


# Format visible interactive elements for snapshots
def _format_interactive_list(
    elements: list[dict],
    region_filter: str | None = None,
    max_items: int = 60,
    skip_noise: bool = True,
) -> list[str]:
    """Format interactive elements as compact snapshot lines."""

    lines = []
    interactive = [e for e in elements if e.get("interactive")]

    if region_filter:
        interactive = [e for e in interactive if e.get("landmark") == region_filter]

    for el in interactive:
        if skip_noise and _is_noise_element(el):
            continue

        if len(lines) >= max_items:
            remaining = len(interactive) - len(lines)
            if remaining > 0:
                lines.append(f"... and {remaining} more (use browser_snapshot for full list)")
            break

        ep = [f'[{el["ref"]}]', el["role"]]
        if el.get("name"):
            ep.append(f'"{el["name"]}"')
        if el.get("value"):
            ep.append(f'value="{el["value"]}"')
        if el.get("disabled"):
            ep.append("(disabled)")
        if el.get("checked") is not None:
            ep.append(f'checked={el["checked"]}')
        lines.append(f"- {' '.join(ep)}")

    return lines


# Snapshot text extraction

# Pull a short text preview from the current page
async def _extract_brief_text(page: Page, max_chars: int = AUTO_TEXT_PREVIEW_LEN) -> str:
    """Extract a short text preview for snapshot output."""

    try:
        text = await page.evaluate("""(maxChars) => {
            // Try main landmark first
            let el = document.querySelector('main, [role="main"]');
            if (!el || !el.innerText || el.innerText.trim().length < 50) {
                el = document.body;
            }
            
            // Strip common noise elements in-place temporarily
            const NOISE = 'nav, footer, header, aside, .comments, [class*="comment"], ' +
                          '[class*="sidebar"], .cookie, [role="banner"], [role="navigation"], ' +
                          '[role="contentinfo"], script, style, [class*="footer"]';
            const hidden = [];
            el.querySelectorAll(NOISE).forEach(n => {
                if (window.getComputedStyle(n).display !== 'none') {
                    hidden.push([n, n.style.display]);
                    n.style.display = 'none';
                }
            });
            
            let text = (el.innerText || el.textContent || '').trim();
            
            // Restore hidden
            hidden.forEach(([n, orig]) => { n.style.display = orig; });
            
            // Collapse whitespace
            text = text.replace(/\\n{3,}/g, '\\n\\n').replace(/[ \\t]{2,}/g, ' ');
            
            if (text.length > maxChars) {
                text = text.substring(0, maxChars) + '\\n[...]';
            }
            return text;
        }""", max_chars)
        return text or ""
    except Exception as exc:
        log.debug(f"Brief text extraction failed: {exc}")
        return ""


# Rendering wait helpers

# Wait until SPA content becomes readable
async def _wait_for_spa_content(page: Page, timeout_ms: int = 5000):
    """Wait for SPA content to settle without relying on fixed sleeps."""

    # Let the network calm down first, but do not fail on long-lived connections.
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass

    # Poll the main landmark until meaningful text appears.
    for _ in range(6):
        try:
            has_content = await page.evaluate("""() => {
                const main = document.querySelector('main, [role="main"]');
                if (!main) return false;
                const text = main.innerText || '';
                // Ignore obvious loading states while content is still rendering.
                if (text.includes('загрузка') || text.includes('Loading')) return false;
                return text.trim().length > 100;
            }""")
            if has_content:
                return
        except Exception:
            pass

        # Use an in-page timer to keep the Playwright transport active.
        try:
            await page.evaluate("() => new Promise(r => setTimeout(r, 500))")
        except Exception:
            await asyncio.sleep(0.5)

    # Give the page one last short rendering window.
    try:
        await page.evaluate("() => new Promise(r => setTimeout(r, 500))")
    except Exception:
        await asyncio.sleep(0.5)


# Overlay and page-state detection
_DISMISS_ACCEPT_TEXTS = [
    "accept all", "accept cookies", "accept", "agree", "allow all",
    "allow cookies", "allow", "i agree", "i accept", "got it",
    "ok", "okay", "close", "dismiss", "continue", "confirm",
    "принять все", "принять", "согласен", "разрешить", "продолжить",
    "хорошо", "ок", "закрыть",
]

_DISMISS_REJECT_TEXTS: list[str] = []

_DISMISS_CLOSE_TEXTS = [
    "no thanks", "no, thanks", "not now", "maybe later", "skip", "skip for now",
    "i'll do it later", "remind me later", "not interested", "cancel",
    "don't show again", "don't show this again", "hide", "hide this",
    "no, i don't want", "no thanks, i don't want", "i don't want discounts",
    "i don't want offers", "i'm not interested",
    "нет, спасибо", "не сейчас", "пропустить", "закрыть", "отмена",
    "не интересует", "напомнить позже",
]

_KNOWN_CLOSE_SELECTORS = [
    "[aria-label='Close']", "[aria-label='close']",
    "[aria-label='Close dialog']", "[aria-label='Dismiss']",
    "[aria-label='dismiss']", "[data-dismiss='modal']",
    ".modal-close", ".popup-close", ".dialog-close",
    ".close-button", ".btn-close", ".close-btn",
    "button.close", "[class*='close'][role='button']",
]

_KNOWN_ACCEPT_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "#accept-cookie-consent",
    ".cc-accept", ".cc-btn.cc-allow",
    "[data-testid='cookie-accept']", "[data-testid='accept-cookies']",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    ".js-accept-cookies", "#js-accept-cookies",
    "[aria-label='Accept cookies']", "[aria-label='Accept all cookies']",
]


# Dismiss common cookie banners and blocking popups
async def _auto_dismiss_overlays(page: Page) -> list[str]:
    """Try to dismiss common overlays before snapshotting."""

    dismissed = []

    # Make a few passes because some banners re-render after the first click.
    for _ in range(3):
        closed_this_pass = False

        # Prefer known selectors before using broad DOM heuristics.
        for sel in _KNOWN_ACCEPT_SELECTORS:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=150):
                    await el.click(timeout=2000)
                    await page.wait_for_timeout(600)
                    dismissed.append(f"selector:{sel}")
                    closed_this_pass = True
                    break
            except Exception:
                pass

        if closed_this_pass:
            continue

        try:
            clicked = await page.evaluate("""(acceptTexts) => {
                const containers = Array.from(document.querySelectorAll(
                    '[id*="cookie"], [id*="consent"], [id*="gdpr"], [id*="banner"], [class*="cookie"], [class*="consent"], [class*="gdpr"], [class*="banner"], [class*="overlay"], [class*="modal"], [role="dialog"], [role="alertdialog"]'
                )).filter(el => {
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    const pos = style.position;
                    if (pos === 'fixed' || pos === 'sticky') return true;
                    return el.offsetParent !== null;
                });

                const normalize = s => s.trim().toLowerCase().replace(/\\s+/g, ' ');

                for (const container of containers) {
                    const btns = Array.from(container.querySelectorAll(
                        'button, [role="button"], a[href="#"], input[type="button"], input[type="submit"]'
                    )).filter(b => b.offsetParent !== null);

                    for (const btn of btns) {
                        const label = normalize(btn.innerText || btn.value || btn.getAttribute('aria-label') || '');
                        if (acceptTexts.some(t => label === t || label.startsWith(t))) {
                            btn.click();
                            return label;
                        }
                    }
                }

                const allBtns = Array.from(document.querySelectorAll('button, [role="button"]'))
                    .filter(b => b.offsetParent !== null);

                for (const btn of allBtns) {
                    const label = normalize(btn.innerText || btn.getAttribute('aria-label') || '');
                    if (acceptTexts.some(t => label === t)) {
                        btn.click();
                        return label;
                    }
                }

                return null;
            }""", _DISMISS_ACCEPT_TEXTS)

            if clicked:
                await page.wait_for_timeout(600)
                dismissed.append(f"js-heuristic:'{clicked}'")
                closed_this_pass = True
        except Exception as e:
            log.debug(f"Overlay JS heuristic error: {e}")

        if not closed_this_pass:
            break

    # Try explicit close buttons on generic modal windows.
    for sel in _KNOWN_CLOSE_SELECTORS:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=100):
                await el.click(timeout=1500)
                await page.wait_for_timeout(400)
                dismissed.append(f"close-selector:{sel}")
                break
        except Exception:
            pass

    # Fall back to close-label heuristics if explicit selectors are missing.
    if not any(d.startswith("close-") for d in dismissed):
        try:
            clicked = await page.evaluate("""(closeTexts) => {
                const normalize = s => s.trim().toLowerCase().replace(/\\s+/g, ' ');

                const containers = Array.from(document.querySelectorAll(
                    '[role="dialog"], [role="alertdialog"], [aria-modal="true"], [class*="modal"], [class*="popup"], [class*="overlay"], [class*="lightbox"]'
                )).filter(el => {
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                    const z = parseInt(style.zIndex) || 0;
                    return el.offsetParent !== null || style.position === 'fixed' || z > 100;
                });

                const fixedHigh = Array.from(document.querySelectorAll('*')).filter(el => {
                    const style = window.getComputedStyle(el);
                    const z = parseInt(style.zIndex) || 0;
                    return style.position === 'fixed' && z > 100 &&
                           style.display !== 'none' && style.visibility !== 'hidden' &&
                           el.offsetWidth > 100 && el.offsetHeight > 50;
                });

                const allContainers = [...new Set([...containers, ...fixedHigh])];

                for (const container of allContainers) {
                    const btns = Array.from(container.querySelectorAll(
                        'button, [role="button"], a'
                    )).filter(b => b.offsetParent !== null || window.getComputedStyle(b).position === 'fixed');

                    for (const btn of btns) {
                        const label = normalize(btn.innerText || btn.getAttribute('aria-label') || btn.getAttribute('title') || '');
                        if (/^[×✕✖x]$/.test(label) || label === 'close') {
                            btn.click();
                            return `icon:${label}`;
                        }
                        if (closeTexts.some(t => label === t || label.startsWith(t))) {
                            btn.click();
                            return label;
                        }
                    }
                }
                return null;
            }""", _DISMISS_CLOSE_TEXTS)

            if clicked:
                await page.wait_for_timeout(500)
                dismissed.append(f"popup-close:'{clicked}'")
        except Exception as e:
            log.debug(f"Popup close heuristic error: {e}")

    # Use Escape as the last low-risk fallback for modal dialogs.
    try:
        has_modal = await page.evaluate("""() => {
            const el = document.querySelector('[role="dialog"],[role="alertdialog"],[aria-modal="true"]');
            if (!el) return false;
            const style = window.getComputedStyle(el);
            return style.display !== 'none' && style.visibility !== 'hidden';
        }""")
        if has_modal:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(400)
            dismissed.append("escape-key")
    except Exception as e:
        log.debug(f"Escape key dismiss error: {e}")

    return dismissed


# Detect situations that may require user guidance
async def _detect_page_situation(page: Page) -> list[str]:
    """Detect page states that should be surfaced in the snapshot."""

    warnings: list[str] = []
    try:
        situation = await page.evaluate("""() => {
            const r = {
                captcha: false, captcha_type: null,
                has_login: false,
                has_cookie_banner: false,
                is_error_page: false, error_type: null,
            };

            if (document.querySelector('iframe[src*="recaptcha"]') ||
                document.querySelector('.g-recaptcha') ||
                document.querySelector('[data-sitekey]') ||
                window.grecaptcha !== undefined) {
                r.captcha = true; r.captcha_type = 'reCAPTCHA';
            }
            if (document.querySelector('iframe[src*="hcaptcha"]') ||
                document.querySelector('.h-captcha') ||
                window.hcaptcha !== undefined) {
                r.captcha = true; r.captcha_type = 'hCaptcha';
            }
            if (document.querySelector('#challenge-form') ||
                document.title.includes('Just a moment') ||
                document.title.includes('Checking your browser')) {
                r.captcha = true; r.captcha_type = 'Cloudflare';
            }
            if (document.querySelector('.cf-turnstile') ||
                document.querySelector('iframe[src*="challenges.cloudflare"]')) {
                r.captcha = true; r.captcha_type = 'Turnstile';
            }

            const pwd = document.querySelector('input[type="password"]');
            if (pwd && pwd.offsetParent !== null) r.has_login = true;

            const cookieSelectors = [
                '#cookie-banner', '#cookie-notice', '#cookie-consent',
                '#cookieConsent', '#cookieBanner', '.cookie-banner',
                '.cookie-notice', '.cookie-consent', '.cookie-bar',
                '[id*="gdpr"]', '[class*="gdpr"]',
                '[aria-label*="cookie"]', '[aria-label*="Cookie"]',
                '#CybotCookiebotDialog', '#onetrust-banner-sdk', '.cc-banner',
            ];
            for (const sel of cookieSelectors) {
                try {
                    const el = document.querySelector(sel);
                    if (el && el.offsetParent !== null) { r.has_cookie_banner = true; break; }
                } catch(e) {}
            }

            const url = window.location.href;
            const title = document.title.toLowerCase();
            const h1 = document.querySelector('h1');
            const h1text = h1 ? h1.textContent.toLowerCase() : '';
            if (url.includes('/404') || title.includes('404') ||
                h1text.includes('not found') || h1text.includes('page not found')) {
                r.is_error_page = true; r.error_type = '404';
            } else if (url.includes('/403') || title.includes('403') ||
                       title.includes('forbidden') || title.includes('access denied')) {
                r.is_error_page = true; r.error_type = '403';
            } else if (title.includes('500') || title.includes('server error') ||
                       h1text.includes('server error')) {
                r.is_error_page = true; r.error_type = '500';
            }

            return r;
        }""")
    except Exception as exc:
        log.warning(f"Situation detection failed: {exc}")
        return warnings

    if situation.get("captcha"):
        ctype = situation.get("captcha_type", "unknown")
        warnings.append(
            f"⚠️ CAPTCHA detected ({ctype}) — "
            f"call browser_wait_for_user to let the user solve it manually."
        )
    if situation.get("has_login"):
        warnings.append(
            "⚠️ Login form detected (password field present) — "
            "call browser_wait_for_user if credentials are needed."
        )
    if situation.get("has_cookie_banner"):
        warnings.append(
            "⚠️ Cookie consent banner detected — "
            "consider clicking the accept button before proceeding."
        )
    if situation.get("is_error_page"):
        etype = situation.get("error_type", "unknown")
        warnings.append(
            f"⚠️ Error page detected (HTTP {etype}) — "
            f"the requested resource may be unavailable."
        )

    return warnings


# Describe a blocking overlay that is still visible
async def _detect_undismissable_overlay(page: Page) -> str | None:
    """Detect a remaining blocking overlay after auto-dismiss attempts."""

    try:
        result = await page.evaluate("""() => {
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            const cx = vw / 2;
            const cy = vh / 2;
            const minArea = vw * vh * 0.15;

            const candidates = Array.from(document.querySelectorAll('*')).filter(el => {
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                const pos = style.position;
                if (pos !== 'fixed' && pos !== 'absolute') return false;
                const z = parseInt(style.zIndex) || 0;
                if (z < 200) return false;
                const rect = el.getBoundingClientRect();
                if (rect.width * rect.height < minArea) return false;
                if (rect.left > cx || rect.right < cx || rect.top > cy || rect.bottom < cy) return false;
                return true;
            });

            if (candidates.length === 0) return null;

            const top = candidates.sort((a, b) => {
                const za = parseInt(window.getComputedStyle(a).zIndex) || 0;
                const zb = parseInt(window.getComputedStyle(b).zIndex) || 0;
                return zb - za;
            })[0];

            const id = top.id ? `#${top.id}` : '';
            const cls = top.className && typeof top.className === 'string'
                ? top.className.trim().split(/\\s+/).slice(0, 3).map(c => `.${c}`).join('') : '';
            const role = top.getAttribute('role') || top.tagName.toLowerCase();
            const text = (top.innerText || '').trim().slice(0, 80);

            const sig = `${id} ${cls} ${role} ${text}`.toLowerCase();
            let kind = 'overlay';
            if (/sign.?up|register|creat.*account|join/.test(sig)) kind = 'registration popup';
            else if (/subscri|newsletter|email/.test(sig)) kind = 'newsletter popup';
            else if (/log.?in|sign.?in|auth/.test(sig)) kind = 'login wall';
            else if (/cookie|consent|gdpr|privacy/.test(sig)) kind = 'cookie banner';
            else if (/age|verify|18/.test(sig)) kind = 'age gate';
            else if (/survey|feedback|rate/.test(sig)) kind = 'survey popup';
            else if (/promo|discount|offer|sale/.test(sig)) kind = 'promo popup';
            else if (/paywall|subscri|premium/.test(sig)) kind = 'paywall';

            return { kind, id, cls, role, text };
        }""")
    except Exception as exc:
        log.debug(f"Overlay detection error: {exc}")
        return None

    if result is None:
        return None

    kind = result.get("kind", "overlay")
    detail = result.get("text", "")[:60]
    return f"{kind}" + (f': "{detail}"' if detail else "")


# Browser lifecycle

# Hold the shared browser context and page
class BrowserState:
    """Store the shared browser session used by MCP tools."""

    def __init__(self):
        """Initialize empty browser state."""

        self._camoufox_cm: AsyncCamoufox | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None


    # Open the browser lazily on first use
    async def ensure_open(self):
        """Launch the browser and register page handlers when needed."""

        if self.page is not None:
            return

        log.info("Launching camoufox browser (Firefox stealth)...")

        try:
            self._camoufox_cm = AsyncCamoufox(
                headless=False,
                window=(BROWSER_WIDTH, BROWSER_HEIGHT),
            )
            browser = await self._camoufox_cm.__aenter__()

            self.context = await browser.new_context(
                viewport={"width": BROWSER_WIDTH, "height": BROWSER_HEIGHT},
                accept_downloads=True,
            )
            self.page = await self.context.new_page()
        except Exception as exc:
            self.page = None
            self.context = None
            if self._camoufox_cm is not None:
                try:
                    await self._camoufox_cm.__aexit__(None, None, None)
                except Exception:
                    pass
            self._camoufox_cm = None
            raise RuntimeError(
                "Browser launch failed. Check that Playwright browsers and Camoufox are installed "
                f"and that the current runtime is allowed to spawn browser subprocesses. Original error: {exc}"
            ) from exc

        # Persist downloads into the shared task directory.
        async def handle_download(download):
            """Save downloaded files into the task directory."""

            log.info(f"Download started: {download.suggested_filename}")
            try:
                DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
                file_path = DOWNLOADS_DIR / download.suggested_filename
                await download.save_as(file_path)
                log.info(f"File saved to: {file_path}")
            except Exception as exc:
                log.error(f"Download failed: {exc}")

        self.page.on("download", handle_download)

        # Auto-accept dialogs so automation does not hang on alerts or prompts.
        async def handle_dialog(dialog):
            """Accept browser dialogs with a deterministic response."""

            log.info(f"Dialog: {dialog.type} - {dialog.message}")
            try:
                if dialog.type == "prompt":
                    await dialog.accept("accepted")
                else:
                    await dialog.accept()
            except Exception as exc:
                log.error(f"Dialog handling failed: {exc}")

        self.page.on("dialog", handle_dialog)
        log.info("Camoufox browser ready.")


    # Close all shared browser resources
    async def close(self):
        """Close the browser context and reset stored references."""

        if self.context:
            await self.context.close()
        if self._camoufox_cm:
            await self._camoufox_cm.__aexit__(None, None, None)
        self.page = None
        self.context = None
        self._camoufox_cm = None


# Shared runtime state
state = BrowserState()
_last_elements: list[dict] = []
_waiting_for_user: bool = False
_nav_history: list[str] = []

# Snapshot builders

# Build the detailed page snapshot returned after navigation
async def _take_snapshot(
    action_context: str | None = None,
    run_dismiss: bool = False,
    include_text: bool = True,
) -> list[TextContent]:
    """Build the full page snapshot used after major page changes."""

    global _last_elements, _nav_history

    # Clear low-value overlays before collecting snapshot data.
    if run_dismiss:
        dismissed = await _auto_dismiss_overlays(state.page)
        if dismissed:
            log.info(f"Auto-dismissed overlays: {dismissed}")

    # Surface blockers that still remain after dismiss attempts.
    blocking = await _detect_undismissable_overlay(state.page)
    overlay_warning = None
    if blocking:
        log.warning(f"Undismissable overlay detected: {blocking}")
        overlay_warning = (
            f"⚠️ OVERLAY: the page has a {blocking} that could not be dismissed automatically. "
            f"Consider calling browser_wait_for_user so the user can close it manually."
        )

    # Refresh the in-memory element cache for later click and type actions.
    elements, tree_text = await get_accessibility_tree(state.page)
    _last_elements = elements

    url = state.page.url
    title = await state.page.title()
    warnings = await _detect_page_situation(state.page)

    # Keep a short navigation trail to help with backtracking.
    if not _nav_history or _nav_history[-1] != url:
        _nav_history.append(url)
        if len(_nav_history) > 20:
            _nav_history.pop(0)

    # Build the textual snapshot in model-friendly sections.
    parts = [
        "## Current page",
        f"**URL:** {url}",
        f"**Title:** {title}",
    ]
    if len(_nav_history) >= 2:
        parts.append(f"**Back URL:** {_nav_history[-2]}")
    if action_context:
        parts.append(f"**Action:** {action_context}")

    main_count = sum(1 for e in elements if e.get("landmark") == "main")
    parts.append(f"**Elements:** {len(elements)} total, {main_count} in main area")

    all_warnings = list(warnings)
    if overlay_warning:
        all_warnings.insert(0, overlay_warning)

    if all_warnings:
        parts.append("\n### ⚠️ Page Situation")
        parts.extend(all_warnings)

    # Include a short text preview so the model can orient itself quickly.
    if include_text:
        brief_text = await _extract_brief_text(state.page)
        if brief_text and len(brief_text.strip()) > 30:
            parts.append(f"\n### Page Text Preview\n{brief_text}")
        else:
            parts.append("\n### Page Text Preview\n(no text content detected — page may still be loading)")

    # Expose the parsed accessibility tree for structural context.
    if tree_text.strip():
        parts.append(f"\n### Accessibility Tree (main area)\n```\n{tree_text}\n```")
    else:
        parts.append("\n### Accessibility Tree\n(empty — page may not have rendered yet)")

    # Finish with the clickable and fillable controls list.
    parts.append("\n### Interactive elements")
    interactive_lines = _format_interactive_list(
        elements, region_filter=None, max_items=MAX_MAIN_INTERACTIVE, skip_noise=True
    )
    if interactive_lines:
        parts.extend(interactive_lines)
    else:
        parts.append("No interactive elements found.")

    return [TextContent(type="text", text="\n".join(parts))]


# Build the smaller snapshot used after in-page actions
async def _take_compact_snapshot(action_context: str | None = None) -> list[TextContent]:
    """Build a compact snapshot for in-page actions."""

    global _last_elements, _nav_history

    elements, _ = await get_accessibility_tree(state.page)
    _last_elements = elements

    url = state.page.url
    title = await state.page.title()

    if not _nav_history or _nav_history[-1] != url:
        _nav_history.append(url)
        if len(_nav_history) > 20:
            _nav_history.pop(0)

    # Keep compact snapshots focused on interactive controls.
    main_count = sum(1 for e in elements if e.get("landmark") == "main")
    parts = [f"**URL:** {url}  |  **Title:** {title}"]
    if action_context:
        parts.append(f"**Action:** {action_context}")
    parts.append(f"**Elements:** {main_count} in main area")
    parts.append("")
    parts.append("### Interactive elements (main area)")

    interactive_lines = _format_interactive_list(
        elements, region_filter="main", max_items=MAX_MAIN_INTERACTIVE, skip_noise=True
    )
    if interactive_lines:
        parts.extend(interactive_lines)
    else:
        # Fall back to the full page if the main region is empty.
        all_lines = _format_interactive_list(
            elements, region_filter=None, max_items=MAX_MAIN_INTERACTIVE, skip_noise=True
        )
        if all_lines:
            parts[-1] = "### Interactive elements"
            parts.extend(all_lines)
        else:
            parts.append("(none)")

    return [TextContent(type="text", text="\n".join(parts))]


# Element lookup and locator resolution

# Find an element by the ref stored in the last snapshot
def _find_element(ref: str) -> dict | None:
    """Return the cached element matching the given ref."""

    for el in _last_elements:
        if el["ref"] == ref:
            return el
    return None


# Resolve the best Playwright locator for a role and name pair
async def _resolve_locator(role: str, name: str):
    """Resolve the best locator for a role and accessible name."""

    # Prefer semantic role lookups because they match the accessibility tree.
    for exact in (True, False):
        try:
            loc = state.page.get_by_role(role, name=name, exact=exact)
            count = await loc.count()
            if count == 0:
                continue
            if count == 1:
                return loc
            for i in range(min(count, 6)):
                try:
                    if await loc.nth(i).is_visible():
                        return loc.nth(i)
                except Exception:
                    continue
            return loc.first
        except Exception:
            continue

    if not name:
        return None

    # Labels are a strong fallback for form fields and controls.
    try:
        loc = state.page.get_by_label(name, exact=False)
        if await loc.count() > 0:
            return loc.first
    except Exception:
        pass

    # Text matching is the broadest fallback when semantic lookup fails.
    for exact in (True, False):
        try:
            loc = state.page.get_by_text(name, exact=exact)
            count = await loc.count()
            if count == 0:
                continue
            for i in range(min(count, 6)):
                try:
                    if await loc.nth(i).is_visible():
                        return loc.nth(i)
                except Exception:
                    continue
        except Exception:
            continue

    return None


# Click actions

# Click a cached accessibility element using safe fallbacks
async def _click_by_role_and_name(ref: str):
    """Click an element referenced by the last accessibility snapshot."""

    elem = _find_element(ref)
    if not elem:
        raise ValueError(
            f"Element ref='{ref}' not found. "
            f"Use browser_snapshot to refresh elements."
        )

    role = elem["role"]
    name = elem.get("name", "")
    is_checkable = role in ("checkbox", "radio", "switch", "menuitemcheckbox", "menuitemradio")

    loc = await _resolve_locator(role, name)
    if loc is None:
        raise ValueError(
            f"Could not locate element ref='{ref}' (role={role}, name='{name}') "
            f"on the page. Try browser_snapshot to get fresh elements."
        )

    last_err: Exception | None = None

    # Try the normal interaction path first.
    try:
        await loc.click(timeout=5000)
        return
    except Exception as e:
        last_err = e

    # Some controls are better handled through Playwright's check helper.
    if is_checkable:
        try:
            await loc.check(force=True, timeout=5000)
            return
        except Exception as e:
            last_err = e

    # Force-click can still work when Playwright thinks the element is obscured.
    try:
        await loc.click(force=True, timeout=5000)
        return
    except Exception as e:
        last_err = e

    # Fall back to DOM click as a last resort.
    try:
        await loc.evaluate("el => el.click()")
        return
    except Exception as e:
        last_err = e

    raise ValueError(
        f"Could not click element ref='{ref}' (role={role}, name='{name}'). "
        f"All click strategies failed. Last error: {last_err}"
    )


# Text input actions

# Fill a cached input-like element with new text
async def _fill_by_role_and_name(ref: str, text: str, clear: bool, press_enter: bool):
    """Fill an input element referenced by the last accessibility snapshot."""

    elem = _find_element(ref)
    if not elem:
        raise ValueError(
            f"Element ref='{ref}' not found. "
            f"Use browser_snapshot to refresh elements."
        )

    role = elem["role"]
    name = elem.get("name", "")

    locator = await _resolve_locator(role, name)

    # Placeholder lookup helps when the accessible name is not exposed as a role name.
    if locator is None and name:
        try:
            loc = state.page.get_by_placeholder(name, exact=False)
            if await loc.count() >= 1:
                locator = loc.first
        except Exception:
            pass

    if locator is None:
        raise ValueError(
            f"Could not locate input ref='{ref}' (role={role}, name='{name}'). "
            f"Try browser_snapshot to refresh."
        )

    if clear:
        # Clear standard inputs first.
        try:
            await locator.fill("")
        except Exception:
            pass

        # Rich text editors often need keyboard-based clearing instead.
        try:
            await locator.press("Control+a")
            await locator.press("Delete")
        except Exception:
            pass

    # Prefer fill(), then fall back to sequential typing for custom editors.
    try:
        await locator.fill(text)
    except Exception:
        await locator.press_sequentially(text, delay=30)

    if press_enter:
        await locator.press("Enter")
