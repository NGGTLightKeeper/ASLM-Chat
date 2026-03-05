"""
main.py — ASLM-UI entry point.

Called by ASLM with a command name and optional flags:
    python main.py runserver [--port PORT] [--log]
    python main.py migrate
    python main.py makemigrations [APPNAME]
    python main.py collectstatic
    python main.py first_run
    python main.py get_setting --key KEY
    python main.py set_setting --key KEY --value VALUE
    python main.py help
"""

import os
import sys
import argparse
import json

# Ensure the project root is on sys.path so Django and Settings can be imported
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ASLM.settings')

from Settings.console import PrintTechData


def run_django_command(*args: str, log: bool = False) -> None:
    """Execute a Django management command via execute_from_command_line."""
    from django.core.management import execute_from_command_line

    argv = ['manage.py', *args]

    if log:
        print(f"[ASLM-UI] Running: {' '.join(argv)}")

    execute_from_command_line(argv)


def cmd_runserver(port: int, log: bool) -> None:
    """Start the Django development server on the given port."""
    if log:
        print(f"[ASLM-UI] Starting server on port {port}...")
    run_django_command('runserver', f'127.0.0.1:{port}', log=log)


def cmd_migrate(log: bool) -> None:
    """Apply all pending database migrations."""
    if log:
        print("[ASLM-UI] Applying migrations...")
    run_django_command('migrate', '--noinput', log=log)


def cmd_makemigrations(app: str | None, log: bool) -> None:
    """Create new migration files for changed models."""
    args = ['makemigrations']
    if app:
        args.append(app)
    run_django_command(*args, log=log)


def cmd_collectstatic(log: bool) -> None:
    """Collect static files into STATIC_ROOT."""
    run_django_command('collectstatic', '--noinput', log=log)


def cmd_first_run(log: bool = True) -> None:
    """Run the first-run setup: generate settings.json and apply migrations."""
    from Settings.first_run import run as first_run
    print("[ASLM-UI] Running first-run setup...")
    first_run(log=log)
    cmd_migrate(log=log)


def cmd_get_setting(key: str) -> None:
    from Settings.settings import get
    val = get(key)
    # Print exactly the value so ASLM can capture it if needed
    print(val if val is not None else "")


def cmd_set_setting(key: str, value: str) -> None:
    from Settings.settings import set
    import json
    # Try to parse numeric or boolean strings back to proper types
    try:
        if value.lower() == 'true':
            val = True
        elif value.lower() == 'false':
            val = False
        else:
            # Check if it's an integer
            val = int(value)
    except (ValueError, TypeError):
        val = value
        
    set(key, val)
    print(f"[ASLM-UI] Setting '{key}' updated to {val}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog='main.py',
        description='ASLM-UI management entry point',
    )
    parser.add_argument('command', type=str, help='Command to execute')
    parser.add_argument('--port', type=int, default=8000,
                        help='Port for runserver (default: 8000)')
    parser.add_argument('--app', type=str, default=None,
                        help='App name for makemigrations')
    parser.add_argument('--key', type=str, default=None,
                        help='Setting key for get_setting/set_setting')
    parser.add_argument('--value', type=str, default=None,
                        help='Setting value for set_setting')
    parser.add_argument('--log', action='store_true',
                        help='Enable verbose output')

    args = parser.parse_args()

    # Django's auto-reloader spawns a child process with RUN_MAIN=true.
    # Print the banner only in the parent to avoid repeating it 2-3 times.
    # Skip for tech commands to keep output clean for ASLM.
    if not os.environ.get('RUN_MAIN') and args.command not in ('get_setting', 'set_setting'):
        PrintTechData().PTD_Print()

    match args.command:
        case 'runserver':
            from Settings.settings import load_settings
            settings = load_settings()
            port = args.port if args.port != 8000 else int(settings.get('port', 8000))
            cmd_runserver(port, log=True)

        case 'migrate':
            cmd_migrate(args.log)

        case 'makemigrations':
            cmd_makemigrations(args.app, args.log)

        case 'collectstatic':
            cmd_collectstatic(args.log)

        case 'first_run':
            cmd_first_run()

        case 'get_setting':
            if not args.key:
                print("Error: --key argument is required.")
                sys.exit(1)
            cmd_get_setting(args.key)
            
        case 'set_setting':
            if not args.key or args.value is None:
                print("Error: --key and --value arguments are required.")
                sys.exit(1)
            cmd_set_setting(args.key, args.value)

        case 'help':
            parser.print_help()

        case _:
            print(f"[ASLM-UI] Unknown command: '{args.command}'")
            print("Run 'python main.py help' for usage.")
            sys.exit(1)


if __name__ == '__main__':
    main()
