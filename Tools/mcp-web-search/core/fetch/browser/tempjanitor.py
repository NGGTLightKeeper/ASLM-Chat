# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Reaper for orphaned browser temp profiles.

Each ``chromium.launch()`` (cloakbrowser → playwright) spins up a throwaway
user-data-dir under the system temp dir — ``playwright_chromiumdev_profile-*``,
plus ``playwright-artifacts-*`` and Chromium's own ``scoped_dir*``. Playwright
removes them on a clean ``browser.close()``, but a force-killed or crashed daemon
(Windows pythonw kill, RSS-recycle crash, idle teardown that never runs) leaks the
whole profile — each one ~120+ files of stale disk cache that never goes away.

Over a long-lived deployment those orphans pile into the "million broken cache
files" the temp dir fills with. The daemon owns the browser lifecycle, so it sweeps
them on startup and after each recycle.

Safety: only dirs whose mtime is older than ``max_age_sec`` are touched, and the age
threshold is kept above the daemon's idle-shutdown window so a *live* profile is
never a candidate (it is either freshly written or the daemon has already exited).
Removal is best-effort per dir — a still-locked dir (held by a running browser) makes
rmtree raise, and we skip it rather than deleting files out from under it.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from pathlib import Path

logger = logging.getLogger("core.fetch.browser.tempjanitor")

# Temp-dir name prefixes created per chromium launch (playwright + chromium itself).
_LEAK_PREFIXES = (
    "playwright_chromiumdev_profile-",
    "playwright-artifacts-",
    "scoped_dir",
)

# Orphans older than this are reaped. Kept above the daemon idle-shutdown (1800s) so a
# live daemon's profile — fresh while serving, gone once idle-shut — is never matched.
_MAX_AGE_SEC = 3600.0


# Remove orphaned browser temp profiles older than max_age_sec. Returns the count reaped.
def sweep_stale_browser_temp(max_age_sec: float = _MAX_AGE_SEC) -> int:
    root = Path(tempfile.gettempdir())
    now = time.time()
    reaped = 0
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        logger.debug("temp janitor: cannot list %s: %s", root, exc)
        return 0
    for entry in entries:
        name = entry.name
        if not entry.is_dir() or not name.startswith(_LEAK_PREFIXES):
            continue
        try:
            age = now - entry.stat().st_mtime
        except OSError:
            continue
        if age < max_age_sec:
            continue  # too fresh — could belong to a live browser
        try:
            shutil.rmtree(entry)  # raises if any file is locked (live profile) → skip
        except OSError as exc:
            logger.debug("temp janitor: skip locked/partial %s: %s", name, exc)
            continue
        reaped += 1
    if reaped:
        logger.info("temp janitor: reaped %d orphaned browser temp dir(s)", reaped)
    return reaped
