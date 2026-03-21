# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import importlib.util
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = BASE_DIR / "Tools"


# Build first-run settings payload
def _build_initial_settings(existing: dict[str, Any], ui_port: int, api_port: int) -> dict[str, Any]:
    """Return the initial settings payload while preserving existing values."""

    initial: dict[str, Any] = dict(existing)
    initial.update(
        {
            "secret_key": existing.get("secret_key") or secrets.token_urlsafe(50),
            "ui-port": existing.get("ui-port", ui_port),
            "api-port": existing.get("api-port", api_port),
            "allowed_hosts": existing.get("allowed_hosts", ["127.0.0.1", "localhost"]),
            "debug": existing.get("debug", False),
            "llm-engine": existing.get("llm-engine", "ollama-service"),
            "lms_url": existing.get("lms_url", "127.0.0.1:1234"),
            "lms_load_config": existing.get("lms_load_config", {}),
            "openai_url": existing.get("openai_url", "127.0.0.1:8000/v1"),
            "openai_api_key": existing.get("openai_api_key", ""),
        }
    )
    return initial

def _print_warning(message: str) -> None:
    """Print a standardized first-run warning message."""

    print(f"[ASLM-Chat] Warning: {message}")

def _run_optional_command(
    command: list[str],
    *,
    description: str,
    log: bool,
    cwd: Path | None = None,
) -> bool:
    """Run one optional bootstrap command without failing the full first-run."""

    if log:
        print(f"[ASLM-Chat] {description}...")

    try:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        _print_warning(f"{description} could not be started: {exc}")
        return False

    if result.stdout and log:
        print(result.stdout.strip())
    if result.stderr and log:
        print(result.stderr.strip())

    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        suffix = f" Details: {details}" if details else ""
        _print_warning(f"{description} failed with exit code {result.returncode}.{suffix}")
        return False

    return True

def _ensure_playwright_browsers(log: bool) -> None:
    """Install Playwright browsers needed by the bundled tools."""

    if importlib.util.find_spec("playwright") is None:
        _print_warning("Skipping Playwright browser install because 'playwright' is not installed.")
        return

    _run_optional_command(
        [sys.executable, "-m", "playwright", "install", "chromium", "firefox"],
        description="Installing Playwright browsers (chromium, firefox)",
        log=log,
    )

def _ensure_camoufox_binary(log: bool) -> None:
    """Download the Camoufox browser binary when available."""

    if importlib.util.find_spec("camoufox") is None:
        _print_warning("Skipping Camoufox fetch because 'camoufox' is not installed.")
        return

    _run_optional_command(
        [sys.executable, "-m", "camoufox", "fetch"],
        description="Fetching Camoufox browser binary",
        log=log,
    )

def _ensure_nltk_data(log: bool) -> None:
    """Download the NLTK datasets expected by the tool stack."""

    try:
        import nltk
    except ImportError:
        _print_warning("Skipping NLTK data bootstrap because 'nltk' is not installed.")
        return

    required_packages = ("punkt", "punkt_tab", "stopwords", "wordnet")
    failed: list[str] = []

    if log:
        print("[ASLM-Chat] Downloading NLTK data packages...")

    for package in required_packages:
        try:
            ok = nltk.download(package, quiet=not log)
        except Exception:
            ok = False
        if not ok:
            failed.append(package)

    if failed:
        _print_warning(f"NLTK data download failed for: {', '.join(failed)}")

def _ensure_spacy_model(log: bool) -> None:
    """Install the default spaCy English model when missing."""

    if importlib.util.find_spec("spacy") is None:
        _print_warning("Skipping spaCy model install because 'spacy' is not installed.")
        return

    if importlib.util.find_spec("en_core_web_sm") is not None:
        if log:
            print("[ASLM-Chat] spaCy model 'en_core_web_sm' is already installed.")
        return

    _run_optional_command(
        [sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
        description="Installing spaCy model en_core_web_sm",
        log=log,
    )

def _run_tool_bootstrap(log: bool) -> None:
    """Run post-dependency bootstrap tasks that were previously handled by install.bat."""

    if not TOOLS_DIR.exists():
        if log:
            print(f"[ASLM-Chat] Tools directory not found, skipping tool bootstrap: {TOOLS_DIR}")
        return

    _ensure_playwright_browsers(log)
    _ensure_camoufox_binary(log)
    _ensure_nltk_data(log)
    _ensure_spacy_model(log)

# Print first-run summary
def _print_summary(settings_file, initial: dict[str, Any]) -> None:
    """Print a short summary of the written first-run settings."""

    print(f"[ASLM-Chat] Settings written to: {settings_file}")
    print(f"[ASLM-Chat]   ui-port    : {initial['ui-port']}")
    print(f"[ASLM-Chat]   api-port   : {initial['api-port']}")
    print(f"[ASLM-Chat]   debug      : {initial['debug']}")
    print(f"[ASLM-Chat]   llm-engine : {initial['llm-engine']}")
    print(f"[ASLM-Chat]   lms_url    : {initial['lms_url']}")
    print(f"[ASLM-Chat]   openai_url : {initial['openai_url']}")
    print("[ASLM-Chat] First-run setup complete.")


# Run first-run setup
def run(log: bool = False, ui_port: int = 30000, api_port: int = 30001) -> None:
    """Create the initial settings file while preserving existing values."""

    from Settings.settings import SETTINGS_FILE, load_settings, save_settings

    existing = load_settings()
    initial = _build_initial_settings(existing, ui_port, api_port)
    save_settings(initial)
    _run_tool_bootstrap(log)

    if log:
        _print_summary(SETTINGS_FILE, initial)
