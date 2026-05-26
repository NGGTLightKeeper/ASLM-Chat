"""Small CLI for talking to sandboxd without MCP."""
from __future__ import annotations

import argparse
import json
import sys

from sandbox_mcp import daemon_client


def main() -> None:
    parser = argparse.ArgumentParser(prog="sandboxctl")
    parser.add_argument("--url", default=None, help="sandboxd URL, default from daemon configuration")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run argv in the sandbox")
    run_parser.add_argument("cmd", nargs=argparse.REMAINDER, help="Command argv after --")

    py_parser = sub.add_parser("python", help="Run Python source in the sandbox")
    py_parser.add_argument("--code", required=True)

    share_parser = sub.add_parser("share", help="Describe a file from /mnt/data/_sandbox")
    share_parser.add_argument("path")
    share_parser.add_argument("--filename")

    sub.add_parser("files", help="List files currently visible in /mnt/data/_sandbox")
    doctor_parser = sub.add_parser("doctor", help="Check sandbox runtime health")
    doctor_parser.add_argument("--repair", action="store_true", help="Recreate unhealthy session container when possible")
    sub.add_parser("status", help="Show daemon session status")
    sub.add_parser("health", help="Check daemon health")
    sub.add_parser("new", help="End the current session and create a new run_id")
    sub.add_parser("end", help="End the current session")
    sub.add_parser("cleanup", help="Run daemon cleanup now")

    args = parser.parse_args()
    try:
        if args.command == "run":
            cmd = args.cmd
            if cmd and cmd[0] == "--":
                cmd = cmd[1:]
            if not cmd:
                raise SystemExit("sandboxctl run requires argv, e.g. sandboxctl run -- python -V")
            print(daemon_client.run({"cmd": cmd}, base_url=args.url))
            return
        if args.command == "python":
            print(daemon_client.run_python(args.code, base_url=args.url))
            return
        if args.command == "share":
            print(json.dumps(daemon_client.share(args.path, args.filename, base_url=args.url), ensure_ascii=False, indent=2))
            return
        if args.command == "files":
            print(json.dumps(daemon_client.files(base_url=args.url), ensure_ascii=False, indent=2))
            return
        if args.command == "doctor":
            print(json.dumps(daemon_client.doctor(repair=args.repair, base_url=args.url), ensure_ascii=False, indent=2))
            return
        if args.command == "status":
            print(json.dumps(daemon_client.status(base_url=args.url), ensure_ascii=False, indent=2))
            return
        if args.command == "health":
            print(json.dumps(daemon_client.health(base_url=args.url), ensure_ascii=False, indent=2))
            return
        if args.command == "new":
            print(json.dumps(daemon_client.session_new(base_url=args.url), ensure_ascii=False, indent=2))
            return
        if args.command == "end":
            print(json.dumps(daemon_client.session_end(base_url=args.url), ensure_ascii=False, indent=2))
            return
        if args.command == "cleanup":
            print(json.dumps(daemon_client.cleanup(base_url=args.url), ensure_ascii=False, indent=2))
            return
    except daemon_client.SandboxDaemonError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
