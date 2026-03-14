"""First-run initialization helpers for ASLM-Chat."""

from __future__ import annotations

import secrets


def run(log: bool = False, ui_port: int = 30000, api_port: int = 30001) -> None:
    """Create the initial settings file while preserving existing values."""
    from Settings.settings import SETTINGS_FILE, load_settings, save_settings

    existing = load_settings()

    initial: dict[str, object] = {
        "secret_key": existing.get("secret_key") or secrets.token_urlsafe(50),
        "ui-port": existing.get("ui-port", ui_port),
        "api-port": existing.get("api-port", api_port),
        "allowed_hosts": existing.get("allowed_hosts", ["127.0.0.1", "localhost"]),
        "debug": existing.get("debug", False),
        "llm-engine": existing.get("llm-engine", "ollama-service"),
    }

    save_settings(initial)

    if log:
        print(f"[ASLM-Chat] Settings written to: {SETTINGS_FILE}")
        print(f"[ASLM-Chat]   ui-port    : {initial['ui-port']}")
        print(f"[ASLM-Chat]   api-port   : {initial['api-port']}")
        print(f"[ASLM-Chat]   debug      : {initial['debug']}")
        print(f"[ASLM-Chat]   llm-engine : {initial['llm-engine']}")
        print("[ASLM-Chat] First-run setup complete.")
