# Copyright NEXTGGTECH. Elastic License 2.0.

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
from urllib.parse import urlparse

logger = logging.getLogger("core.fetch.onion.tor_proxy")

# Standard tor SOCKS ports we opportunistically reuse: 9050 = system tor daemon,
# 9150 = Tor Browser's bundled tor.
_REUSE_PORTS = (9050, 9150)

_lock = threading.Lock()
_UNSET = object()                             # sentinel: resolution not yet attempted
_resolved: str | None | object = _UNSET       # cached socks url (None = resolved-to-unavailable)


# Receive an exact SOCKS response fragment or fail when the listener closes early.
def _recv_exact(connection: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = connection.recv(remaining)
        if not chunk:
            raise OSError("SOCKS listener closed the connection")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


# Verify that the endpoint speaks SOCKS5 and accepts Tor's default no-auth method.
def _socks5_open(socks_url: str, timeout: float = 1.0) -> bool:
    try:
        endpoint = urlparse(socks_url)
        if (
            endpoint.scheme not in {"socks5", "socks5h"}
            or not endpoint.hostname
            or not endpoint.port
        ):
            return False
        with socket.create_connection(
            (endpoint.hostname, endpoint.port), timeout=timeout
        ) as connection:
            connection.settimeout(timeout)
            connection.sendall(b"\x05\x01\x00")
            return _recv_exact(connection, 2) == b"\x05\x00"
    except (OSError, ValueError):
        logger.debug("SOCKS5 validation failed for %s", socks_url, exc_info=True)
        return False


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
            if _socks5_open(cfg.socks_url):
                result = cfg.socks_url
        # 2. Reuse a running tor (system daemon, then Tor Browser).
        if result is None:
            for port in _REUSE_PORTS:
                candidate = f"socks5h://127.0.0.1:{port}"
                if _socks5_open(candidate):
                    result = candidate
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
