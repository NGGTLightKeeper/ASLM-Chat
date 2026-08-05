# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import importlib.util
import re
import secrets
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = BASE_DIR / "Tools"


# True when a venv's package manifest declares the given distribution (any version pin).
# Lets browser-binary bootstrap follow what each venv actually installs rather than a
# hardcoded tool list — tools stay independent, the installer just reads their manifests.
def _venv_declares(packages: list[str], dist: str) -> bool:
    dist = dist.lower()
    for spec in packages:
        name = re.split(r"[<>=!~;\[ ]", spec, 1)[0].strip().lower()
        if name == dist:
            return True
    return False


# Build the initial settings payload for the first run.
def _build_initial_settings(
    existing: dict[str, Any],
    ui_port: int,
    api_port: int,
) -> dict[str, Any]:
    initial: dict[str, Any] = dict(existing)
    initial.update(
        {
            "secret_key": existing.get("secret_key") or secrets.token_urlsafe(50),
            "ui-port": existing.get("ui-port", ui_port),
            "api-port": existing.get("api-port", api_port),
            "ollama-service_port": existing.get("ollama-service_port", 20003),
            "allowed_hosts": existing.get("allowed_hosts", ["127.0.0.1", "localhost"]),
            "debug": existing.get("debug", False),
            "llm-engine": existing.get("llm-engine", "ollama-service"),
            "lms_url": existing.get("lms_url", "127.0.0.1:1234"),
            "openai_url": existing.get("openai_url", "127.0.0.1:8000/v1"),
            "openai_api_key": existing.get("openai_api_key", ""),
            "google_genai_url": existing.get("google_genai_url", "generativelanguage.googleapis.com"),
            "google_genai_api_key": existing.get("google_genai_api_key", ""),
        }
    )
    return initial


# Print a standardized bootstrap warning.
def _print_warning(message: str) -> None:
    print(f"[ASLM-Chat] Warning: {message}")


# Run an optional bootstrap command without failing the full first-run setup.
def _run_optional_command(
    command: list[str],
    *,
    description: str,
    log: bool,
    cwd: Path | None = None,
) -> bool:
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


# Install Playwright browsers needed by the bundled tools.
def _ensure_playwright_browsers(venv_id: str, log: bool) -> None:
    from Services import venv_manager

    python_path = venv_manager.get_venv_python(venv_id)
    if not python_path.exists():
        _print_warning(f"Skipping Playwright browser install because venv '{venv_id}' is missing.")
        return

    _run_optional_command(
        [str(python_path), "-m", "playwright", "install", "chromium", "firefox"],
        description=f"Installing Playwright browsers for {venv_id} (chromium, firefox)",
        log=log,
    )


# Download the Camoufox browser binary when the venv is available.
def _ensure_camoufox_binary(venv_id: str, log: bool) -> None:
    from Services import venv_manager

    python_path = venv_manager.get_venv_python(venv_id)
    if not python_path.exists():
        _print_warning(f"Skipping Camoufox fetch because venv '{venv_id}' is missing.")
        return

    _run_optional_command(
        [str(python_path), "-m", "camoufox", "fetch"],
        description=f"Fetching Camoufox browser binary for {venv_id}",
        log=log,
    )


# Download the NLTK datasets expected by the tool stack.
def _ensure_nltk_data(log: bool) -> None:
    from Services import venv_manager

    code = """
import nltk
failed = []
for package in ("punkt", "punkt_tab", "stopwords", "wordnet"):
    try:
        ok = nltk.download(package, quiet=False)
    except Exception:
        ok = False
    if not ok:
        failed.append(package)
if failed:
    raise SystemExit("NLTK data download failed for: " + ", ".join(failed))
"""
    if not venv_manager.run_venv_code("mcp-web-search", code, log=log):
        _print_warning("NLTK data bootstrap did not complete successfully.")


# Install the default spaCy English model when missing.
def _ensure_spacy_model(log: bool) -> None:
    from Services import venv_manager

    code = """
import importlib.util
import subprocess
import sys
if importlib.util.find_spec("en_core_web_sm") is None:
    raise SystemExit(subprocess.call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"]))
print("[ASLM-Chat] spaCy model 'en_core_web_sm' is already installed.")
"""
    if not venv_manager.run_venv_code("mcp-web-search", code, log=log):
        _print_warning("spaCy model bootstrap did not complete successfully.")


# Run post-dependency bootstrap tasks for bundled tools.
def _run_tool_bootstrap(log: bool) -> None:
    from Services import venv_manager

    if not venv_manager.ensure_all(log=log):
        _print_warning("One or more ASLM-Chat venvs did not install successfully.")

    if not TOOLS_DIR.exists():
        if log:
            print(f"[ASLM-Chat] Tools directory not found, skipping tool bootstrap: {TOOLS_DIR}")
        return

    # Provision browser binaries per what each venv's manifest declares, so this stays
    # correct as tools add/drop browser backends (e.g. web search retiring Camoufox for
    # the warm cloakbrowser) without editing a hardcoded tool list here.
    bootstrap_tasks: list[tuple[Any, str]] = []
    for cfg in venv_manager.iter_venv_configs():
        venv_id = str(cfg.get("id") or "")
        if not venv_id:
            continue
        packages = list(cfg.get("packages", [])) + list(cfg.get("packages_no_deps", []))
        if _venv_declares(packages, "playwright"):
            bootstrap_tasks.append((_ensure_playwright_browsers, venv_id))
        if _venv_declares(packages, "camoufox"):
            bootstrap_tasks.append((_ensure_camoufox_binary, venv_id))

    # Run the per-venv browser fetches in parallel; each task isolates its own failures,
    # and as_completed surfaces any stray exception as a warning without aborting setup.
    if bootstrap_tasks:
        with ThreadPoolExecutor(max_workers=len(bootstrap_tasks)) as executor:
            futures = [
                executor.submit(task, venv_id, log)
                for task, venv_id in bootstrap_tasks
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    _print_warning(f"Browser bootstrap task failed: {exc}")


# Print a short summary of the written first-run settings.
def _print_summary(settings_file: Path, initial: dict[str, Any]) -> None:
    print(f"[ASLM-Chat] Settings written to: {settings_file}")
    print(f"[ASLM-Chat]   ui-port    : {initial['ui-port']}")
    print(f"[ASLM-Chat]   api-port   : {initial['api-port']}")
    print(f"[ASLM-Chat]   ollama-port: {initial.get('ollama-service_port', 20003)}")
    print(f"[ASLM-Chat]   debug      : {initial['debug']}")
    print(f"[ASLM-Chat]   llm-engine : {initial['llm-engine']}")
    print(f"[ASLM-Chat]   lms_url    : {initial['lms_url']}")
    print(f"[ASLM-Chat]   openai_url : {initial['openai_url']}")
    print(f"[ASLM-Chat]   google_url : {initial['google_genai_url']}")
    print("[ASLM-Chat] First-run setup complete.")


# Run the first-run setup workflow.
def run(
    log: bool = False,
    ui_port: int = 20000,
    api_port: int = 20001,
) -> None:
    from Settings.settings import SETTINGS_FILE, load_settings, save_settings

    existing = load_settings()
    initial = _build_initial_settings(existing, ui_port, api_port)
    save_settings(initial)

    from Settings.mcp_json import ensure_default_mcp_json

    ensure_default_mcp_json()
    from Settings.skills import ensure_skills_dir

    ensure_skills_dir()

    _run_tool_bootstrap(log)

    if log:
        _print_summary(SETTINGS_FILE, initial)
