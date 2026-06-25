# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Resolve a usable tor SOCKS proxy — reuse first, spawn (from an installed binary) last.

Resolution order (all gated behind tor.enabled):
  1. explicit config socks_url, if it answers;
  2. a running tor: system daemon on 9050, then an open Tor Browser on 9150;
  3. spawn our own — ONLY from a tor binary already present on the system (PATH or a known
     Tor Browser location). Never downloaded/installed by us.
No tor found → return None and the onion layer goes no-op.
"""

from __future__ import annotations

import atexit
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger("core.fetch.onion.tor_proxy")

# Standard tor SOCKS ports we opportunistically reuse: 9050 = system tor daemon,
# 9150 = Tor Browser's bundled tor.
_REUSE_PORTS = (9050, 9150)
# Dedicated port for a tor WE spawn, off the standard ones so we never collide with a
# tor we failed to detect.
_OWN_SOCKS_PORT = 9250

_lock = threading.Lock()
_UNSET = object()                             # sentinel: resolution not yet attempted
_resolved: str | None | object = _UNSET       # cached socks url (None = resolved-to-unavailable)
_proc: subprocess.Popen | None = None         # our spawned tor, if any
_last_used = 0.0                              # monotonic time of the last onion fetch
_idle_stop: threading.Event | None = None     # signals the idle watchdog to exit
_warming = False                              # a background prewarm is in flight
_warm_thread: threading.Thread | None = None


# Record onion activity — resets the spawned tor's idle timer. Called per onion fetch.
def mark_used() -> None:
    global _last_used
    _last_used = time.monotonic()


# Kick a background tor warmup (spawn + first circuit) so the first onion fetch isn't cold.
# Idempotent, non-blocking, deduped, and gated on tor.enabled + tor.prewarm. If tor is already
# up it just refreshes the idle timer (keeps it warm while tools are flowing); if a prior
# resolve found no tor (None) it does nothing. The worker is a tracked daemon thread bounded by
# resolve_socks's own bootstrap timeout — not a fire-and-forget leak.
def prewarm() -> None:
    global _warming, _warm_thread
    try:
        from core.config import load_search_config

        cfg = load_search_config().tor
    except Exception:  # noqa: BLE001
        return
    if not cfg.enabled or not cfg.prewarm:
        return
    with _lock:
        if _warming or _resolved is None:
            return                       # already warming, or known-unavailable this process
        if _resolved is not _UNSET:
            mark_used()                  # already warm → keep it warm
            return
        _warming = True

    def _run() -> None:
        global _warming
        try:
            if resolve_socks():
                mark_used()
        finally:
            with _lock:
                _warming = False

    _warm_thread = threading.Thread(target=_run, name="tor-prewarm", daemon=True)
    _warm_thread.start()


# True when something accepts a TCP connection on host:port.
def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


# The tor binary's path under a "Tor Browser" folder (the dir name is constant; only the
# parent — Desktop / OneDrive / wherever it was extracted — varies and may be localized).
def _tb_tail() -> Path:
    leaf = "tor.exe" if sys.platform == "win32" else "tor"
    return Path("Browser") / "TorBrowser" / "Tor" / leaf


# Dirs not worth descending in a scan (huge/noisy/irrelevant) — keeps the walk fast.
_SCAN_PRUNE = frozenset({
    "windows", "$recycle.bin", "node_modules", "system volume information",
    "programdata", "program files", "program files (x86)", "appdata", "$windows.~bt",
})


# Match any OS's Tor Browser tor binary by its structural tail (a "Tor" dir holding the
# binary) plus a "tor browser" marker in the path. Covers all three layouts:
#   win   …/Tor Browser/Browser/TorBrowser/Tor/tor.exe
#   linux …/tor-browser*/Browser/TorBrowser/Tor/tor
#   macOS /Applications/Tor Browser.app/Contents/MacOS/Tor/tor
def _looks_like_tb_tor(path: str, leaf: str) -> bool:
    norm = path.strip().replace("\\", "/").lower()
    return (
        norm.endswith("/tor/" + leaf)
        and ("tor browser" in norm or "tor-browser" in norm or "torbrowser" in norm)
        and Path(path.strip()).is_file()
    )


# Query the OS's standard file index — Spotlight (mdfind) on macOS, locate/plocate on Linux —
# instead of walking the disk. Pre-installed, so zero-install holds. No-op on Windows (no
# standard CLI index; we don't pull in Everything) → discovery falls back to the scan there.
def _indexer_lookup() -> str | None:
    leaf = "tor.exe" if sys.platform == "win32" else "tor"
    cmd: list[str] | None = None
    if sys.platform == "darwin":
        cmd = ["mdfind", "-name", leaf]
    elif sys.platform.startswith("linux"):
        tool = shutil.which("plocate") or shutil.which("locate")
        if tool:
            cmd = [tool, "-i", "torbrowser/tor/" + leaf]
    if not cmd:
        return None
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
    except Exception:  # noqa: BLE001 — indexer missing/slow → fall through to the scan
        return None
    for line in out.stdout.splitlines():
        if _looks_like_tb_tor(line, leaf):
            return line.strip()
    return None


# Bounded filesystem scan: find a "Tor Browser" folder under likely roots, deadline-capped so
# it can never hang. Structural (matches the folder name, not a hardcoded localized path), so
# it finds tor wherever it was extracted — OneDrive, a localized Desktop, a custom dir.
def _scan_for_tor_browser(*, budget_sec: float = 4.0) -> str | None:
    home = Path.home()
    one = os.environ.get("OneDrive", "")
    # Likely parents first (near-instant hit), then the profile/OneDrive roots as fallback.
    roots = [home / "Desktop", home / "Downloads", home / "Documents"]
    if one:
        roots += [Path(one), Path(one) / "Desktop"]
    roots.append(home)
    tail = _tb_tail()
    deadline = time.monotonic() + budget_sec
    seen: set[str] = set()
    for root in roots:
        rk = str(root).lower()
        if rk in seen or not root.is_dir():
            continue
        seen.add(rk)
        for dirpath, dirnames, _ in os.walk(root):
            if time.monotonic() > deadline:
                return None
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") and d.lower() not in _SCAN_PRUNE]
            for d in dirnames:
                if d.lower() == "tor browser":
                    cand = Path(dirpath) / d / tail
                    if cand.is_file():
                        return str(cand)
    return None


# Locate an already-installed tor binary. Tiers, fastest first: PATH → OS standard index
# (mdfind/locate; no-op on Windows) → bounded folder scan. None when tor isn't present —
# we never install it.
def discover_tor_binary(override: str = "") -> str | None:
    if override:
        return override if Path(override).is_file() else None
    found = shutil.which("tor")
    if found:
        return found
    hit = _indexer_lookup()
    if hit:
        return hit
    if sys.platform == "darwin":
        # /Applications is outside the home-rooted scan, so check the canonical spot directly.
        mac = Path("/Applications/Tor Browser.app/Contents/MacOS/Tor/tor")
        if mac.is_file():
            return str(mac)
    return _scan_for_tor_browser()


# Spawn our own tor from an installed binary and wait until it serves SOCKS. Returns the
# socks url or None. The process is tracked module-side and killed at interpreter exit.
def _spawn_tor(binary: str, *, bootstrap_timeout: float = 90.0,
               idle_timeout: float = 900.0) -> str | None:
    global _proc
    data_dir = Path(tempfile.mkdtemp(prefix="aslm-tor-"))
    # Detach into its own process group/session so we can kill the whole tree and a
    # parent-console Ctrl-C can't reach it — matches the browser daemon's spawn discipline.
    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    try:
        _proc = subprocess.Popen(
            [binary, "--SocksPort", str(_OWN_SOCKS_PORT), "--DataDirectory", str(data_dir),
             "--ControlPort", "0", "--Log", "warn stdout"],
            **kwargs,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("tor spawn failed (%s): %s", binary, exc)
        return None
    atexit.register(_terminate)
    socks = f"socks5h://127.0.0.1:{_OWN_SOCKS_PORT}"
    deadline = time.monotonic() + bootstrap_timeout
    while time.monotonic() < deadline:
        if _proc.poll() is not None:
            logger.warning("spawned tor exited early (code=%s)", _proc.returncode)
            return None
        if _port_open("127.0.0.1", _OWN_SOCKS_PORT) and tor_health(socks):
            logger.info("spawned tor ready on %s", socks)
            mark_used()
            _start_idle_watch(idle_timeout)
            return socks
        time.sleep(1.0)
    logger.warning("spawned tor did not bootstrap within %.0fs", bootstrap_timeout)
    _terminate()
    return None


# Reap the spawned tor if it has been idle past the timeout (0 = never). Returns True when
# it tore the process down. Pure check + terminate — the watchdog loop just calls this.
def _reap_if_idle(idle_timeout: float) -> bool:
    global _resolved
    if _proc is None or idle_timeout <= 0:
        return False
    if time.monotonic() - _last_used < idle_timeout:
        return False
    logger.info("spawned tor idle >= %.0fs — shutting down", idle_timeout)
    _terminate()
    with _lock:
        _resolved = _UNSET  # let the next onion need re-resolve (reuse or respawn)
    return True


# Background watchdog: self-terminate the spawned tor after idle_timeout with no onion
# fetch, mirroring the warm-browser daemon's idle shutdown.
def _start_idle_watch(idle_timeout: float) -> None:
    global _idle_stop
    if idle_timeout <= 0:
        return
    _idle_stop = threading.Event()
    stop = _idle_stop

    def _loop() -> None:
        while not stop.wait(min(30.0, idle_timeout)):
            if _reap_if_idle(idle_timeout):
                return

    threading.Thread(target=_loop, name="tor-idle-watch", daemon=True).start()


# Kill our spawned tor and any children, idempotently and within a bound. terminate →
# (5s) → kill escalation so a wedged tor can never hang teardown or leak a process tree.
def _terminate() -> None:
    global _proc, _idle_stop
    if _idle_stop is not None:
        _idle_stop.set()  # stop the idle watchdog
        _idle_stop = None
    proc, _proc = _proc, None
    if proc is None or proc.poll() is not None:
        return
    try:
        import psutil

        p = psutil.Process(proc.pid)
        tree = p.children(recursive=True) + [p]
        for node in tree:
            try:
                node.terminate()
            except Exception:  # noqa: BLE001
                pass
        _, alive = psutil.wait_procs(tree, timeout=5)
        for node in alive:
            try:
                node.kill()
            except Exception:  # noqa: BLE001
                pass
        return
    except Exception:  # noqa: BLE001 — psutil missing/failed: bounded terminate→kill on the proc
        pass
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


# Confirm a SOCKS url actually exits through Tor (curl check.torproject.org → IsTor:true).
def tor_health(socks_url: str, timeout: float = 30.0) -> bool:
    try:
        from curl_cffi import requests as _r

        r = _r.get("https://check.torproject.org/api/ip",
                   impersonate="chrome124",
                   proxies={"http": socks_url, "https": socks_url}, timeout=timeout)
        return bool(r.json().get("IsTor"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("tor health check failed for %s: %s", socks_url, exc)
        return False


# Resolve (and cache) a usable tor SOCKS url, or None when unavailable/disabled.
def resolve_socks(force: bool = False) -> str | None:
    global _resolved
    with _lock:
        if _resolved is not _UNSET and not force:
            return _resolved  # type: ignore[return-value]

        from core.config import load_search_config

        cfg = load_search_config().tor
        result: str | None = None

        if not cfg.enabled:
            _resolved = None
            return None

        # 1. Explicit override.
        if cfg.socks_url:
            host_port = cfg.socks_url.rsplit("/", 1)[-1]
            host, _, port = host_port.partition(":")
            if port.isdigit() and _port_open(host or "127.0.0.1", int(port)):
                result = cfg.socks_url
        # 2. Reuse a running tor (system daemon, then Tor Browser).
        if result is None:
            for port in _REUSE_PORTS:
                if _port_open("127.0.0.1", port):
                    result = f"socks5h://127.0.0.1:{port}"
                    logger.info("reusing running tor SOCKS on %d", port)
                    break
        # 3. Spawn our own from an installed binary (never installed by us).
        if result is None and cfg.spawn_own:
            binary = discover_tor_binary(cfg.tor_binary)
            if binary:
                logger.info("no running tor; spawning from %s", binary)
                result = _spawn_tor(binary, idle_timeout=cfg.idle_shutdown_sec)
            else:
                logger.info("tor enabled but no tor binary found — onion layer disabled")

        _resolved = result
        return result
