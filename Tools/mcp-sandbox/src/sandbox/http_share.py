# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import mimetypes
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

from sandbox.config import HTTP_HOST, HTTP_PORT
from sandbox.token_registry import _get_token_info


# Share request handler.

class FileShareHandler(SimpleHTTPRequestHandler):
    """Serve shared files and HTML app previews."""

    # Silence default HTTP request logging.

    def log_message(self, format, *args):  # noqa: A003
        """Suppress noisy request logs."""

        return None


    # Route incoming share requests.

    def do_GET(self):  # noqa: N802
        """Dispatch download and app-preview requests."""

        path = unquote(self.path)

        if path.startswith("/dl/"):
            token = path[4:].split("/")[0].split("?")[0]
            self._serve_download(token)
            return

        if path.startswith("/app/"):
            parts = path[5:].split("/", 1)
            token = parts[0]
            subpath = parts[1] if len(parts) > 1 else ""
            self._serve_app(token, subpath)
            return

        self.send_error(404, "Not Found")


    # File download handling.

    def _serve_download(self, token: str) -> None:
        """Serve a shared file by token."""

        info = _get_token_info(token)
        if not info or info["type"] != "file":
            self.send_error(404, "Token not found or expired")
            return

        filepath = info["path"]
        if not os.path.isfile(filepath):
            self.send_error(404, "File not found")
            return

        try:
            filename = os.path.basename(filepath)
            mime_type, _ = mimetypes.guess_type(filename)
            mime_type = mime_type or "application/octet-stream"

            with open(filepath, "rb") as file_handle:
                content = file_handle.read()

            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{filename}"',
            )
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
        except Exception as exc:  # pragma: no cover
            self.send_error(500, str(exc))


    # HTML app preview handling.

    def _serve_app(self, token: str, subpath: str) -> None:
        """Serve a file from a shared app directory."""

        info = _get_token_info(token)
        if not info or info["type"] != "dir":
            self.send_error(404, "Token not found or expired")
            return

        base_dir = info["path"]
        if not subpath or subpath == "/":
            subpath = "index.html"

        # Decode percent-encoding a second time to catch double-encoded
        # traversal sequences like %252e%252e%252f → %2e%2e%2f → ../
        subpath = unquote(subpath)

        # Strip any leading slashes so os.path.join can't treat it as absolute.
        subpath = subpath.lstrip("/")

        safe_path = os.path.normpath(os.path.join(base_dir, subpath))
        norm_base = os.path.normpath(base_dir)
        if not (safe_path == norm_base or safe_path.startswith(norm_base + os.sep)):
            self.send_error(403, "Access denied")
            return

        if not os.path.isfile(safe_path):
            self.send_error(404, "File not found")
            return

        try:
            mime_type, _ = mimetypes.guess_type(safe_path)
            mime_type = mime_type or "application/octet-stream"

            with open(safe_path, "rb") as file_handle:
                content = file_handle.read()

            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
        except Exception as exc:  # pragma: no cover
            self.send_error(500, str(exc))


_http_server = None
_http_thread = None


# HTTP server lifecycle.

def _start_http_server() -> None:
    """Start the share server in a background thread."""

    global _http_server, _http_thread

    if _http_server is not None:
        return

    try:
        _http_server = ThreadingHTTPServer((HTTP_HOST, HTTP_PORT), FileShareHandler)
        _http_thread = threading.Thread(
            target=_http_server.serve_forever,
            daemon=True,
        )
        _http_thread.start()
    except Exception as exc:  # pragma: no cover
        print(
            f"Warning: Could not start HTTP server on port {HTTP_PORT}: {exc}",
            file=sys.stderr,
        )


def _stop_http_server() -> None:
    """Stop the share server and join its thread."""

    global _http_server, _http_thread

    if _http_server is None:
        return

    try:
        _http_server.shutdown()
        _http_server.server_close()
    finally:
        if _http_thread is not None:
            _http_thread.join(timeout=5)

        _http_server = None
        _http_thread = None
