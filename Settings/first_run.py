"""
Settings/first_run.py — ASLM-Chat first-run initializer.

Called once after installation (via 'python main.py first_run').
Generates Settings/settings.json with a random secret key and
default values. Safe to re-run: preserves existing keys.
"""

import secrets
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def run(log: bool = False, ui_port: int = 30000, api_port: int = 30001) -> None:
    """
    Generate settings.json if it does not already exist or is empty.

    Parameters
    ----------
    log : bool
        Print progress messages when True.
    ui_port : int
        Django server port. ASLM passes the allocated UI port here.
    """
    from Settings.settings import SETTINGS_FILE, load_settings, save_settings

    existing = load_settings()

    # Build the initial settings, keeping any values already present.
    initial: dict = {
        # Cryptographic secret — regenerate only if missing or blank.
        'secret_key': existing.get('secret_key') or secrets.token_urlsafe(50),

        # Network
        'ui-port': existing.get('ui-port', ui_port),
        'api-port': existing.get('api-port', api_port),
        'allowed_hosts': existing.get('allowed_hosts', ['127.0.0.1', 'localhost']),

        # Security
        'debug': existing.get('debug', False),
    }

    save_settings(initial)

    if log:
        print(f"[ASLM-Chat] Settings written to: {SETTINGS_FILE}")
        print(f"[ASLM-Chat]   ui-port    : {initial['ui-port']}")
        print(f"[ASLM-Chat]   api-port   : {initial['api-port']}")
        print(f"[ASLM-Chat]   debug      : {initial['debug']}")
        print("[ASLM-Chat] First-run setup complete.")
