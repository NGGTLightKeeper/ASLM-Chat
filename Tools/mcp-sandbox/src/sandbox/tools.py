# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import base64
import mimetypes
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mcp.types import ImageContent, TextContent

from sandbox.config import (
    DEFAULT_TASK_DIR,
    DEFAULT_TIMEOUT,
    HTTP_HOST,
    HTTP_PORT,
    TOKEN_TTL_SECONDS,
)
from sandbox.container import (
    exec_bash,
    get_status,
    reset_container,
    restore_container,
    snapshot_container,
)
from sandbox.token_registry import _register_token
from sandbox.workspace import (
    clear_workspace,
    copy_into_workspace,
    get_secure_task_path,
    list_directory as list_workspace_directory,
    normalize_relative_path,
    read_file as read_workspace_file,
    str_replace as replace_in_workspace_file,
    write_file as write_workspace_file,
)


# Share payload builders.

def _share_file(path: Path) -> dict:
    """Build share metadata for a downloadable file."""

    token = _register_token(str(path), "file")
    filename = path.name
    url = f"http://{HTTP_HOST}:{HTTP_PORT}/dl/{token}"
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)

    return {
        "ok": True,
        "kind": "file",
        "url": url,
        "markdown": f"[Download {filename}]({url})",
        "filename": filename,
        "expires_in_seconds": TOKEN_TTL_SECONDS,
        "expires_at": expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def _share_app(directory: Path, entry_file: str) -> dict:
    """Build share metadata for a previewable web app."""

    token = _register_token(str(directory), "dir")
    url = f"http://{HTTP_HOST}:{HTTP_PORT}/app/{token}/{entry_file}"
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)

    return {
        "ok": True,
        "kind": "web_app",
        "url": url,
        "markdown": f"[Open {entry_file}]({url})",
        "entry_file": entry_file,
        "expires_in_seconds": TOKEN_TTL_SECONDS,
        "expires_at": expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


# MCP tool registration.

def register_tools(mcp) -> None:
    """Register sandbox tools on a FastMCP instance."""


    # Runtime inspection tools.

    @mcp.tool()
    def status() -> dict:
        """Return current sandbox and Docker status."""

        return get_status()


    # Workspace browsing tools.

    @mcp.tool()
    def list_directory(path: str = ".", recursive: bool = False, max_depth: int = 3) -> dict:
        """List files and directories inside the task workspace."""

        try:
            return list_workspace_directory(
                path=path,
                recursive=recursive,
                max_depth=max_depth,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


    @mcp.tool()
    def read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> dict:
        """Read a text file from the task workspace."""

        try:
            return read_workspace_file(path, start_line=start_line, end_line=end_line)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


    # Workspace editing tools.

    @mcp.tool()
    def write_file(path: str, content: str) -> dict:
        """Create or fully overwrite a text file in the task workspace."""

        try:
            return write_workspace_file(path, content)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


    @mcp.tool()
    def str_replace(path: str, old_str: str, new_str: str) -> dict:
        """Replace one exact unique text fragment in a file."""

        try:
            return replace_in_workspace_file(path, old_str, new_str)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


    # Container execution tools.

    @mcp.tool()
    def bash(
        command: str,
        cwd: str = ".",
        timeout_s: int = DEFAULT_TIMEOUT,
        stdin: str | None = None,
    ) -> dict:
        """Run a bash command inside the Linux sandbox container."""

        try:
            return exec_bash(command=command, cwd=cwd, timeout_s=timeout_s, stdin=stdin)
        except Exception as exc:
            return {
                "ok": False,
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "error": str(exc),
                "elapsed_ms": 0,
                "truncated": False,
            }


    # Artifact presentation tools.

    @mcp.tool()
    def show_image(path: str) -> list:
        """Load an image from the workspace into chat."""

        try:
            target = get_secure_task_path(path)
        except Exception as exc:
            return [TextContent(type="text", text=f"Error: {exc}")]

        if not target.is_file():
            return [
                TextContent(
                    type="text",
                    text=f"Error: File not found: {normalize_relative_path(path)}",
                )
            ]

        mime_type, _ = mimetypes.guess_type(str(target))
        if not mime_type or not mime_type.startswith("image/"):
            return [
                TextContent(
                    type="text",
                    text=f"Error: File is not an image: {normalize_relative_path(path)}",
                )
            ]

        try:
            with open(target, "rb") as file_handle:
                b64_data = base64.b64encode(file_handle.read()).decode("utf-8")

            return [ImageContent(type="image", data=b64_data, mimeType=mime_type)]
        except Exception as exc:
            return [TextContent(type="text", text=f"Error reading image: {exc}")]


    @mcp.tool()
    def share(path: str) -> dict:
        """Create a localhost share link for a file or HTML app."""

        try:
            target = get_secure_task_path(path)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        if not target.exists():
            return {
                "ok": False,
                "error": f"Path not found: {normalize_relative_path(path)}",
            }

        if target.is_file():
            if target.suffix.lower() == ".html":
                return _share_app(target.parent, target.name)

            return _share_file(target)

        index_html = target / "index.html"
        if index_html.is_file():
            return _share_app(target, "index.html")

        return {
            "ok": False,
            "error": f"Directory has no index.html: {normalize_relative_path(path)}",
        }


    # Host import tools.

    @mcp.tool()
    def import_from_host(host_path: str, dest_path: str | None = None) -> dict:
        """Copy an allowed host path into the task workspace."""

        try:
            result = copy_into_workspace(host_path=host_path, dest_path=dest_path)
            if dest_path is None:
                result["default_task_dir"] = "."
                result["model_workspace_root"] = DEFAULT_TASK_DIR

            return result
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


    # Container reset and snapshot tools.

    @mcp.tool()
    def reset(preserve_workspace: bool = True) -> dict:
        """Recreate the sandbox container from the base image."""

        try:
            result = reset_container(preserve_workspace=preserve_workspace)
            if result.get("ok") and not preserve_workspace:
                result["workspace_cleanup"] = clear_workspace()

            return result
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


    @mcp.tool()
    def snapshot(name: str = "stable") -> dict:
        """Save the current container state as a named snapshot."""

        try:
            return snapshot_container(name=name)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


    @mcp.tool()
    def restore(name: str = "stable", preserve_workspace: bool = True) -> dict:
        """Restore the container from a previously created snapshot."""

        try:
            result = restore_container(
                name=name,
                preserve_workspace=preserve_workspace,
            )
            if result.get("ok") and not preserve_workspace:
                result["workspace_cleanup"] = clear_workspace()

            return result
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
