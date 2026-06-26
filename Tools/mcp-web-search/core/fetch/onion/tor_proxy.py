# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Resolve a usable tor SOCKS proxy by REUSING a tor that is already running.

Resolution order (all gated behind tor.enabled):
  1. explicit config socks_url, if it answers;
  2. a running tor: system daemon on 9050, then an open Tor Browser on 9150.
No running tor found → return None and the onion layer goes no-op.

We deliberately do NOT spawn our own tor. Discovering an installed tor binary on disk is a
fragile whack-a-mole (Desktop / OneDrive / localized folders / AppData / custom dirs) and the
spawn lifecycle (process groups, idle-watchdog, tree-kill) was the most bug-prone part of the
layer for an edge case the user can cover by simply opening Tor Browser. So: bring your own
running tor (system service or Tor Browser), or set tor.socks_url explicitly.
"""

from __future__ import annotations

import logging
import socket
import threading

logger = logging.getLogger("core.fetch.onion.tor_proxy")

# Standard tor SOCKS ports we opportunistically reuse: 9050 = system tor daemon,
# 9150 = Tor Browser's bundled tor.
_REUSE_PORTS = (9050, 9150)

_lock = threading.Lock()
_UNSET = object()                             # sentinel: resolution not yet attempted
_resolved: str | None | object = _UNSET       # cached socks url (None = resolved-to-unavailable)


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


# Resolve (and cache) a usable tor SOCKS url, or None when unavailable/disabled. Pure probing —
# no process is ever spawned. `force` re-probes (e.g. after the user starts Tor Browser).
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
        if result is None:
            logger.info("tor enabled but no running tor found (start Tor Browser or a tor "
                        "daemon, or set tor.socks_url) — onion layer disabled")

        _resolved = result
        return result


# Drop the cached resolution so the next call re-probes (tests / after starting tor).
def reset() -> None:
    global _resolved
    with _lock:
        _resolved = _UNSET
