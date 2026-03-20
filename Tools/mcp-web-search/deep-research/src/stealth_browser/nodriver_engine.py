# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger("stealth.nodriver")


# Nodriver-based stealth browser engine.
class NodriverEngine:
    # Configure Nodriver launch settings.
    def __init__(
        self,
        headless: bool = True,
        timeout_sec: float = 30.0,
        user_agent: Optional[str] = None,
        proxy: Optional[str] = None,
        locale: str = "en-US",
    ):
        self.headless = headless
        self.timeout_sec = timeout_sec
        self.user_agent = user_agent
        self.proxy = proxy
        self.locale = locale
        self._available: Optional[bool] = None

    # Check whether Nodriver can be used.
    def is_available(self) -> bool:
        """Return True when Nodriver is installed and ready."""

        if self._available is not None:
            return self._available
        try:
            import nodriver  # noqa: F401

            self._available = True
        except Exception:
            self._available = False
            logger.debug("nodriver not installed - engine disabled")
        return self._available

    # Extract one page with Nodriver.
    async def extract(self, url: str, wait_sec: float = 3.0) -> Optional[Dict]:
        """Open a page, wait briefly, and return its HTML."""

        if not self.is_available():
            return None

        import nodriver as uc

        browser = None
        try:
            config = uc.Config()
            config.headless = self.headless

            if self.user_agent:
                config.add_argument(f"--user-agent={self.user_agent}")
            if self.proxy:
                config.add_argument(f"--proxy-server={self.proxy}")

            browser = await uc.start(config)
            page = await browser.get(url)

            await asyncio.sleep(wait_sec)

            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                await asyncio.sleep(1.0)
            except Exception:
                pass

            html = await page.get_content()
            if not html or len(html) < 200:
                return None

            return {
                "html": html,
                "url": url,
                "method": "nodriver",
            }

        except asyncio.TimeoutError:
            logger.warning("nodriver timeout: %s", url)
            return None
        except Exception as exc:
            msg = " ".join(str(exc).split())
            fatal_markers = (
                "failed to connect to browser",
                "failed to connect to the browser",
                "cannot find chrome binary",
                "cannot find chromium binary",
                "no such file or directory",
            )
            if any(marker in msg.lower() for marker in fatal_markers):
                self._available = False
                logger.warning("nodriver disabled for this run after startup error")
            logger.warning("nodriver error for %s: %s", url, msg[:280])
            return None
        finally:
            if browser:
                try:
                    browser.stop()
                except Exception:
                    pass

    # Extract multiple pages with a concurrency cap.
    async def extract_batch(
        self,
        urls: list[str],
        max_concurrency: int = 3,
        wait_sec: float = 3.0,
    ) -> list[Optional[Dict]]:
        """Run Nodriver extraction for a batch of URLs."""

        sem = asyncio.Semaphore(max_concurrency)

        # Run one URL under the batch semaphore.
        async def _limited(url: str) -> Optional[Dict]:
            async with sem:
                return await asyncio.wait_for(
                    self.extract(url, wait_sec=wait_sec),
                    timeout=self.timeout_sec,
                )

        tasks = [_limited(u) for u in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r if isinstance(r, dict) else None for r in results]
