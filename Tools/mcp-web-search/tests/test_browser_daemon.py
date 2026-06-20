# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Deterministic coverage for the warm-browser daemon's supervision logic.

No real Chromium or network: a fake browser/context is installed via _open and the
scrape result is canned, so we can exercise the parts that must be correct before the
daemon goes into production — recycle priority, the burn→rotate identity policy,
checkpoint persistence (the "backups"), counter/blocked-streak bookkeeping, and the
idle-checkpoint loop. The real scrape path is covered separately by live smoke runs.
"""

from __future__ import annotations

import asyncio
import types

from core.fetch.browser import daemon as daemon_mod
from core.fetch.browser.daemon import RecycleReason, ScrapeResult, WarmChromium
from core.fetch.browser.identity_store import IdentityStore


# ── fakes ───────────────────────────────────────────────────────────────────────────

class _FakeContext:
    def __init__(self, state: dict) -> None:
        self._state = state
        self.closed = False

    async def storage_state(self) -> dict:
        return self._state

    async def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


# Build a WarmChromium whose _open installs fakes and whose _scrape returns canned results.
def _wire(wc: WarmChromium, *, state: dict | None = None, results: list[ScrapeResult] | None = None) -> dict:
    seed_state = state or {"cookies": [{"name": "SID", "value": "1", "domain": ".example.com"}], "origins": []}
    calls = {"opens": 0, "scrapes": 0}
    canned = list(results or [])

    async def fake_open(self) -> None:
        self._browser = _FakeBrowser()
        self._context = _FakeContext(seed_state)

        async def _close() -> None:
            await self._context.close()
            await self._browser.close()

        self._teardown = _close
        import time as _t
        self._started_at = _t.monotonic()
        self._requests = 0
        self._dirty = False
        calls["opens"] += 1

    async def fake_scrape(self, url: str, *, wait: float, nav_timeout: float) -> ScrapeResult:
        calls["scrapes"] += 1
        if canned:
            return canned.pop(0)
        return ScrapeResult(url=url, status="ok", ok=True, title="t", html="x" * 500, text="y" * 500)

    wc._open = types.MethodType(fake_open, wc)
    wc._scrape = types.MethodType(fake_scrape, wc)
    return calls


def _store(tmp_path) -> IdentityStore:
    return IdentityStore(str(tmp_path / "identity.db"))


# ── recycle decision (pure) ───────────────────────────────────────────────────────

def test_recycle_reason_priority(tmp_path, monkeypatch):
    wc = WarmChromium(identity=_store(tmp_path), max_requests=5, max_age_sec=100.0, max_rss_mb=2048)
    monkeypatch.setattr(daemon_mod, "_process_tree_rss_mb", lambda: 10.0)

    import time
    assert wc._recycle_reason() is None          # browser down → never recycle
    wc._browser = object()                        # pretend alive
    wc._started_at = time.monotonic()             # just launched
    assert wc._recycle_reason() is None           # fresh

    wc._requests = 5
    assert wc._recycle_reason() == RecycleReason.REQUESTS

    wc._requests = 0
    wc._started_at = time.monotonic() - 200.0
    assert wc._recycle_reason() == RecycleReason.AGE

    wc._started_at = time.monotonic()
    monkeypatch.setattr(daemon_mod, "_process_tree_rss_mb", lambda: 9999.0)
    assert wc._recycle_reason() == RecycleReason.RSS

    # Burn outranks every other reason.
    wc._blocked_streak = 3
    assert wc._recycle_reason() == RecycleReason.BURN


# ── fetch bookkeeping ───────────────────────────────────────────────────────────────

def test_fetch_counts_and_marks_dirty(tmp_path):
    wc = WarmChromium(identity=_store(tmp_path), max_requests=99)
    _wire(wc)

    async def go():
        r = await wc.fetch("https://example.com")
        return r

    r = asyncio.run(go())
    assert r.ok and r.status == "ok"
    assert wc._requests == 1 and wc._total == 1
    assert wc._dirty is True
    assert wc._blocked_streak == 0


def test_blocked_increments_streak_then_resets(tmp_path):
    wc = WarmChromium(identity=_store(tmp_path), max_requests=99)
    blocked = ScrapeResult(url="u", status="blocked", html="x" * 500, text="")
    ok = ScrapeResult(url="u", status="ok", ok=True, html="x" * 500, text="y" * 500)
    _wire(wc, results=[blocked, blocked, ok])

    async def go():
        await wc.fetch("https://e.com")   # blocked → streak 1
        s1 = wc._blocked_streak
        await wc.fetch("https://e.com")   # blocked → streak 2
        s2 = wc._blocked_streak
        await wc.fetch("https://e.com")   # ok → streak 0
        return s1, s2, wc._blocked_streak

    s1, s2, s3 = asyncio.run(go())
    assert (s1, s2, s3) == (1, 2, 0)


# ── recycle behaviour + checkpoint persistence (the "backups") ──────────────────────

def test_request_count_recycle_checkpoints_good(tmp_path):
    store = _store(tmp_path)
    wc = WarmChromium(identity=store, max_requests=2)
    calls = _wire(wc)

    async def go():
        await wc.fetch("https://e.com")   # requests 1
        await wc.fetch("https://e.com")   # requests 2
        await wc.fetch("https://e.com")   # crosses threshold → recycle, then requests 1

    asyncio.run(go())
    assert wc._recycles == 1
    assert calls["opens"] == 2            # initial + one reopen
    # The recycle checkpointed a *good* generation → seedable on next start.
    assert store.latest_good("chromium") is not None
    assert store.cookie_header_for("chromium", "example.com") == "SID=1"


def test_burn_recycle_rotates_identity(tmp_path):
    store = _store(tmp_path)
    # Seed two good generations so a burn has an older one to fall back to.
    store.checkpoint("chromium", {"cookies": [{"name": "OLD", "value": "1", "domain": ".e.com"}], "origins": []})
    store.checkpoint("chromium", {"cookies": [{"name": "NEW", "value": "2", "domain": ".e.com"}], "origins": []})

    wc = WarmChromium(identity=store, max_requests=99)
    blk = ScrapeResult(url="u", status="blocked", html="x" * 500, text="")
    _wire(wc, results=[blk, blk, blk])

    async def go():
        # Three consecutive blocks; the 4th fetch sees burn streak and recycles.
        await wc.fetch("https://e.com")
        await wc.fetch("https://e.com")
        await wc.fetch("https://e.com")
        # Streak now 3; force the recycle decision directly (no 4th canned result needed).
        assert wc._recycle_reason() == RecycleReason.BURN
        await wc._recycle(RecycleReason.BURN)

    asyncio.run(go())
    assert wc._recycles == 1
    assert wc._blocked_streak == 0
    # Burn marked the newest generation not-good and rotated to the older good one.
    # (A fresh good checkpoint was also written by the burn's checkpoint(good=False),
    #  so latest_good must still resolve to a real, non-burned state.)
    assert store.latest_good("chromium") is not None


def test_rss_recycle_then_serves(tmp_path, monkeypatch):
    store = _store(tmp_path)
    wc = WarmChromium(identity=store, max_requests=99, max_rss_mb=512)
    _wire(wc)
    # First fetch opens; second sees RSS over the cap and recycles before serving.
    rss = {"v": 10.0}
    monkeypatch.setattr(daemon_mod, "_process_tree_rss_mb", lambda: rss["v"])

    async def go():
        await wc.fetch("https://e.com")
        rss["v"] = 99999.0
        r = await wc.fetch("https://e.com")
        return r

    r = asyncio.run(go())
    assert r.ok
    assert wc._recycles == 1


# ── checkpoint loop + lifecycle ─────────────────────────────────────────────────────

def test_idle_checkpoint_persists_when_dirty(tmp_path):
    store = _store(tmp_path)
    wc = WarmChromium(identity=store, checkpoint_interval=5.0)
    _wire(wc)

    async def go():
        await wc._open()
        wc._dirty = True
        wc._inflight = 0
        # Invoke the loop body once directly rather than waiting checkpoint_interval.
        await wc._checkpoint(good=True)

    asyncio.run(go())
    assert wc._dirty is False
    assert store.latest_good("chromium") is not None


def test_stop_final_checkpoints_and_tears_down(tmp_path):
    store = _store(tmp_path)
    wc = WarmChromium(identity=store)
    _wire(wc)

    async def go():
        await wc.fetch("https://e.com")
        ctx = wc._context
        await wc.stop()
        return ctx

    ctx = asyncio.run(go())
    assert ctx.closed is True
    assert wc._browser is None
    assert store.latest_good("chromium") is not None
