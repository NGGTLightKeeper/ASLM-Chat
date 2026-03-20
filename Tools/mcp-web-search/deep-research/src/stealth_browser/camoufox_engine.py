# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import logging
import random
from pathlib import Path
import warnings
from typing import Dict, List, Optional

warnings.filterwarnings(
    "ignore",
    message=r".*urllib3 .* doesn't match a supported version.*",
    category=Warning,
    module=r"requests",
)

try:
    from ..config import (
        CAMOUFOX_PROFILE_LOCALES,
        CAMOUFOX_PROFILE_OS_WEIGHTS,
        CAMOUFOX_WARMUP_COUNT,
        CAMOUFOX_WARMUP_URLS,
    )
except (ImportError, ValueError):
    CAMOUFOX_WARMUP_URLS = ["https://www.wikipedia.org/"]
    CAMOUFOX_WARMUP_COUNT = 1
    CAMOUFOX_PROFILE_LOCALES = ["en-US"]
    CAMOUFOX_PROFILE_OS_WEIGHTS = {"windows": 0.7, "macos": 0.2, "linux": 0.1}

logger = logging.getLogger("stealth.camoufox")


# Camoufox-based stealth browser engine.
class CamoufoxEngine:
    # Static browser profile pools.
    _UA_BY_OS = {
        "windows": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        ],
        "macos": [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.6; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:123.0) Gecko/20100101 Firefox/123.0",
        ],
        "linux": [
            "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
        ],
    }
    _SCREEN_POOL = [
        {"width": 1366, "height": 768},
        {"width": 1440, "height": 900},
        {"width": 1536, "height": 864},
        {"width": 1920, "height": 1080},
        {"width": 1600, "height": 900},
    ]
    _TZ_BY_LOCALE = {
        "en-US": ["America/New_York", "America/Chicago", "America/Los_Angeles"],
        "en-GB": ["Europe/London"],
        "en-CA": ["America/Toronto", "America/Vancouver"],
        "de-DE": ["Europe/Berlin"],
    }
    _PLATFORM_BY_OS = {
        "windows": "Win32",
        "macos": "MacIntel",
        "linux": "Linux x86_64",
    }

    # Configure Camoufox launch and profile settings.
    def __init__(
        self,
        headless: bool = True,
        timeout_sec: float = 45.0,
        proxy: Optional[dict] = None,
        locale: str = "en-US",
        humanize: bool = True,
        geoip: bool = False,
        warmup_urls: Optional[List[str]] = None,
        warmup_count: Optional[int] = None,
        profile_locales: Optional[List[str]] = None,
        profile_os_weights: Optional[Dict[str, float]] = None,
    ):
        self.headless = headless
        self.timeout_sec = timeout_sec
        self.proxy = proxy
        self.locale = locale
        self.humanize = humanize
        self.geoip = geoip
        self.warmup_urls = list(warmup_urls or CAMOUFOX_WARMUP_URLS)
        self.warmup_count = int(CAMOUFOX_WARMUP_COUNT if warmup_count is None else warmup_count)
        self.profile_locales = list(profile_locales or CAMOUFOX_PROFILE_LOCALES or [locale])
        self.profile_os_weights = dict(profile_os_weights or CAMOUFOX_PROFILE_OS_WEIGHTS)
        self._available: Optional[bool] = None

    # Check whether Camoufox is installed and usable.
    def is_available(self) -> bool:
        """Return True when the Camoufox runtime is available."""

        if self._available is not None:
            return self._available
        try:
            import camoufox  # noqa: F401
            from camoufox.pkgman import INSTALL_DIR, LAUNCH_FILE, OS_NAME

            launch_rel = LAUNCH_FILE.get(OS_NAME)
            if not launch_rel:
                self._available = False
                return self._available

            install_dir = Path(str(INSTALL_DIR))
            if OS_NAME == "mac":
                launch_path = (install_dir / "Camoufox.app" / "Contents" / "Resources" / launch_rel).resolve()
            else:
                launch_path = install_dir / launch_rel

            if not launch_path.exists():
                self._available = False
                logger.debug("camoufox executable not found at %s - engine disabled", launch_path)
                return self._available
            self._available = True
        except Exception as exc:
            self._available = False
            logger.debug("camoufox not available - engine disabled: %s", exc)
        return self._available

    # Pick an operating system by configured weights.
    def _pick_weighted_os(self) -> str:
        """Choose an OS profile according to configured weights."""

        keys = list(self.profile_os_weights.keys())
        if not keys:
            return "windows"
        weights = [max(0.0, float(self.profile_os_weights.get(k, 0.0))) for k in keys]
        total = sum(weights)
        if total <= 0:
            return random.choice(keys)
        return random.choices(keys, weights=weights, k=1)[0]

    # Build one browser profile for the next session.
    def _build_profile(self) -> Dict:
        """Assemble one randomized browser profile."""

        os_name = self._pick_weighted_os()
        locale = random.choice(self.profile_locales) if self.profile_locales else self.locale
        timezone_pool = self._TZ_BY_LOCALE.get(locale, ["UTC"])
        timezone = random.choice(timezone_pool)
        screen = dict(random.choice(self._SCREEN_POOL))
        ua_pool = self._UA_BY_OS.get(os_name, self._UA_BY_OS["windows"])
        user_agent = random.choice(ua_pool)

        return {
            "os": os_name,
            "locale": locale,
            "timezone": timezone,
            "screen": screen,
            "user_agent": user_agent,
            "platform": self._PLATFORM_BY_OS.get(os_name, "Win32"),
        }

    # Apply the profile to a new page.
    async def _profile_page(self, page, profile: Dict) -> None:
        """Inject profile settings into the page."""

        init_script = (
            "Object.defineProperty(navigator, 'language', {get: () => '%s'});"
            "Object.defineProperty(navigator, 'languages', {get: () => ['%s', 'en']});"
            "Object.defineProperty(navigator, 'platform', {get: () => '%s'});"
            "try { Intl.DateTimeFormat = Intl.DateTimeFormat; } catch (e) {}"
        ) % (profile["locale"], profile["locale"], profile["platform"])

        try:
            await page.add_init_script(init_script)
        except Exception:
            pass

        try:
            await page.set_extra_http_headers(
                {
                    "Accept-Language": f"{profile['locale']},en;q=0.7",
                    "User-Agent": profile["user_agent"],
                }
            )
        except Exception:
            pass

        try:
            await page.set_viewport_size(profile["screen"])
        except Exception:
            pass

    # Simulate light user interactions.
    async def _human_actions(self, page) -> None:
        """Perform a few simple actions to reduce static browsing patterns."""

        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.25)")
            await asyncio.sleep(random.uniform(0.35, 0.9))
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.6)")
            await asyncio.sleep(random.uniform(0.25, 0.8))
        except Exception:
            pass

        try:
            viewport = await page.evaluate(
                "({w: window.innerWidth || 1280, h: window.innerHeight || 720})"
            )
            max_w = int(viewport.get("w", 1280))
            max_h = int(viewport.get("h", 720))
            await page.mouse.move(random.randint(20, max(25, max_w - 20)), random.randint(20, max(25, max_h - 20)))
        except Exception:
            pass

    # Visit warm-up pages before the target URL.
    async def _warmup(self, page) -> None:
        """Warm up the browser session before loading the target page."""

        if not self.warmup_urls:
            return

        count = max(1, self.warmup_count)
        if len(self.warmup_urls) <= count:
            warm_targets = list(self.warmup_urls)
        else:
            warm_targets = random.sample(self.warmup_urls, count)

        for warm_url in warm_targets:
            try:
                await page.goto(
                    warm_url,
                    timeout=max(5000, int(self.timeout_sec * 250)),
                    wait_until="domcontentloaded",
                )
                await asyncio.sleep(random.uniform(0.7, 1.6))
                await self._human_actions(page)
            except Exception:
                continue

    # Extract HTML from a live browser session.
    async def _extract_with_browser(self, browser, url: str, wait_sec: float, profile: Dict) -> Optional[Dict]:
        """Open the target URL and return extracted HTML when present."""

        page = await browser.new_page()
        await self._profile_page(page, profile)

        # Always do warm-up before visiting target URL.
        await self._warmup(page)

        await page.goto(
            url,
            timeout=int(self.timeout_sec * 1000),
            wait_until="domcontentloaded",
        )
        await asyncio.sleep(wait_sec)
        await self._human_actions(page)

        html = await page.content()
        if not html or len(html) < 200:
            return None

        return {
            "html": html,
            "url": url,
            "method": "camoufox",
            "profile": profile,
        }

    # Extract one page with Camoufox.
    async def extract(self, url: str, wait_sec: float = 4.0) -> Optional[Dict]:
        """Run one Camoufox extraction request."""

        if not self.is_available():
            return None

        from camoufox.async_api import AsyncCamoufox

        profile = self._build_profile()
        launch_kwargs = {
            "headless": self.headless,
            "humanize": self.humanize,
            "geoip": self.geoip,
            "locale": profile["locale"],
        }
        if self.proxy:
            launch_kwargs["proxy"] = self.proxy

        try:
            async with AsyncCamoufox(**launch_kwargs) as browser:
                return await self._extract_with_browser(browser, url, wait_sec=wait_sec, profile=profile)
        except asyncio.TimeoutError:
            logger.warning("camoufox timeout: %s", url)
            return None
        except Exception as exc:
            msg = str(exc).lower()
            fatal_markers = (
                "failed to launch",
                "executable doesn't exist",
                "camoufox is not installed",
                "no attribute 'is_set'",
            )
            if any(marker in msg for marker in fatal_markers):
                self._available = False
            logger.warning("camoufox error for %s: %s", url, exc)
            return None

    # Extract multiple pages with limited concurrency.
    async def extract_batch(
        self,
        urls: List[str],
        max_concurrency: int = 2,
        wait_sec: float = 4.0,
    ) -> List[Optional[Dict]]:
        """Run Camoufox extraction for a batch of URLs."""

        sem = asyncio.Semaphore(max_concurrency)

        # Run one URL under the batch semaphore.
        async def _limited(url: str) -> Optional[Dict]:
            async with sem:
                return await asyncio.wait_for(self.extract(url, wait_sec=wait_sec), timeout=self.timeout_sec)

        tasks = [_limited(u) for u in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r if isinstance(r, dict) else None for r in results]
