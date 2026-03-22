# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import argparse
import importlib
import os
import sys


# Prepare project imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ASLM.settings")

from Settings.console import PrintTechData


# Run Django command
def run_django_command(*args: str, log: bool = False) -> None:
    """Execute a Django management command."""

    from django.core.management import execute_from_command_line

    argv = ["manage.py", *args]
    if log:
        print(f"[ASLM-Chat] Running: {' '.join(argv)}")

    execute_from_command_line(argv)

# Start Django development server
def cmd_runserver(port: int, log: bool) -> None:
    """Start the Django development server on the requested port."""

    if log:
        print(f"[ASLM-Chat] Starting server on port {port} (noreload)...")

    # ASLM tracks the launched process directly. Django's autoreloader would
    # spawn a child interpreter and can confuse the module runner into
    # thinking the service stopped, so keep a single long-lived process here.
    run_django_command("runserver", f"127.0.0.1:{port}", "--noreload", log=log)

# Apply database migrations
def cmd_migrate(log: bool) -> None:
    """Apply all pending database migrations."""

    if log:
        print("[ASLM-Chat] Applying migrations...")

    run_django_command("migrate", "--noinput", log=log)

# Create migration files
def cmd_makemigrations(app: str | None, log: bool) -> None:
    """Create migration files for changed models."""

    args = ["makemigrations"]
    if app:
        args.append(app)

    run_django_command(*args, log=log)

# Collect static files
def cmd_collectstatic(log: bool) -> None:
    """Collect static files into ``STATIC_ROOT``."""

    run_django_command("collectstatic", "--noinput", log=log)


# Run first-time setup
def cmd_first_run(log: bool = True, ui_port: int = 30000, api_port: int = 30001) -> None:
    """Generate settings and apply initial migrations."""

    from Settings.first_run import run as first_run

    print("[ASLM-Chat] Running first-run setup...")
    first_run(log=log, ui_port=ui_port, api_port=api_port)
    cmd_migrate(log=log)

# Read one runtime setting
def cmd_get_setting(key: str) -> None:
    """Print a single setting value for ASLM integration hooks."""

    from Settings.settings import get

    value = get(key)
    print(value if value is not None else "")

# Update one runtime setting
def cmd_set_setting(key: str, value: str) -> None:
    """Update a single setting key from string input."""

    from Settings.settings import normalize_setting_value, set

    parsed_value = normalize_setting_value(value)
    set(key, parsed_value)
    print(f"[ASLM-Chat] Setting '{key}' updated to {parsed_value}")

# Install YaCy DB snapshot
def cmd_install_yacy_db(log: bool = True) -> None:
    """Download the optional YaCy database snapshot into the managed runtime."""

    from Services import yacy_service

    ok = yacy_service.ensure_database_snapshot(log=log)
    if not ok:
        print("[ASLM-Chat] YaCy database snapshot installation did not complete successfully.")
        sys.exit(1)

    print("[ASLM-Chat] YaCy database snapshot is ready.")


# Start local engine service
def maybe_start_local_engine_service(log: bool) -> None:
    """Start the active local engine service when the current adapter needs it."""

    from Settings import settings

    if not settings.is_ollama_engine(settings.get_llm_engine()):
        return

    try:
        ollama_service = importlib.import_module("Services.ollama-service")
        ollama_service.start_ollama()
    except ImportError as exc:
        if log:
            print(f"[ASLM-Chat] Warning: Services.ollama-service could not be loaded. {exc}")


# Build CLI parser
def _build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser for the project entry point."""

    parser = argparse.ArgumentParser(
        prog="main.py",
        description="ASLM-Chat management entry point",
    )
    parser.add_argument("command", type=str, help="Command to execute")
    parser.add_argument("--port", type=int, default=30000, help="Port for runserver (default: 30000)")
    parser.add_argument("--api-port", type=int, default=30001, help="API server port (default: 30001)")
    parser.add_argument("--app", type=str, default=None, help="App name for makemigrations")
    parser.add_argument("--key", type=str, default=None, help="Setting key for get_setting/set_setting")
    parser.add_argument("--value", type=str, default=None, help="Setting value for set_setting")
    parser.add_argument("--log", action="store_true", help="Enable verbose output")
    return parser

# Print startup banner
def _maybe_print_banner(command: str) -> None:
    """Print technical module data once for interactive commands."""

    if not os.environ.get("RUN_MAIN") and command not in {"get_setting", "set_setting"}:
        PrintTechData().PTD_Print()

# Resolve runtime server port
def _resolve_runserver_port(requested_port: int) -> int:
    """Return the effective UI port for ``runserver``."""

    from Settings.settings import load_settings

    if requested_port != 30000:
        return requested_port

    runtime_settings = load_settings()
    return int(runtime_settings.get("ui-port", 30000))


# Dispatch CLI command
def main() -> None:
    """Parse CLI arguments and dispatch the requested command."""

    parser = _build_parser()
    args = parser.parse_args()

    _maybe_print_banner(args.command)

    match args.command:
        case "runserver":
            port = _resolve_runserver_port(args.port)

            # Start the managed local engine once before Django's reloader spins
            # up the child process that serves requests.
            if not os.environ.get("RUN_MAIN"):
                maybe_start_local_engine_service(args.log)

            cmd_runserver(port, log=args.log)

        case "migrate":
            cmd_migrate(args.log)

        case "makemigrations":
            cmd_makemigrations(args.app, args.log)

        case "collectstatic":
            cmd_collectstatic(args.log)

        case "first_run":
            cmd_first_run(log=True, ui_port=args.port, api_port=args.api_port)

        case "get_setting":
            if not args.key:
                print("Error: --key argument is required.")
                sys.exit(1)
            cmd_get_setting(args.key)

        case "set_setting":
            if not args.key or args.value is None:
                print("Error: --key and --value arguments are required.")
                sys.exit(1)
            cmd_set_setting(args.key, args.value)

        case "install_yacy_db":
            cmd_install_yacy_db(log=True)

        case "help":
            parser.print_help()

        case _:
            print(f"[ASLM-Chat] Unknown command: '{args.command}'")
            print("Run 'python main.py help' for usage.")
            sys.exit(1)


if __name__ == "__main__":
    main()
