"""
Settings/first_run.py — ASLM-UI first-run initializer.

Called once after installation (via 'python main.py first_run').
Generates Settings/settings.json with a random secret key and
default values. Safe to re-run: preserves existing keys.
"""

import secrets
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def run(log: bool = False, port: int = 8000, ollama_url: str = 'http://127.0.0.1:11434') -> None:
    """
    Generate settings.json if it does not already exist or is empty.

    Parameters
    ----------
    log : bool
        Print progress messages when True.
    port : int
        Django server port. ASLM passes the allocated port here.
    ollama_url : str
        Base URL of the local Ollama service.
    """
    from Settings.settings import SETTINGS_FILE, load_settings, save_settings

    existing = load_settings()

    # Build the initial settings, keeping any values already present.
    initial: dict = {
        # Cryptographic secret — regenerate only if missing or blank.
        'secret_key': existing.get('secret_key') or secrets.token_urlsafe(50),

        # Network
        'port': existing.get('port', port),
        'allowed_hosts': existing.get('allowed_hosts', ['127.0.0.1', 'localhost']),

        # Security
        'debug': existing.get('debug', False),

        # Ollama integration
        'ollama_url': existing.get('ollama_url', ollama_url),
    }

    save_settings(initial)

    if log:
        print(f"[ASLM-UI] Settings written to: {SETTINGS_FILE}")
        print(f"[ASLM-UI]   port       : {initial['port']}")
        print(f"[ASLM-UI]   debug      : {initial['debug']}")
        print(f"[ASLM-UI]   ollama_url : {initial['ollama_url']}")
        print("[ASLM-UI] First-run setup complete.")
