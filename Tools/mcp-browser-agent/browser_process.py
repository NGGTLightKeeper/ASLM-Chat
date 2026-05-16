# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from browser_portal import append_browser_portal_debug_event


SERVER_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_ROOT.parent.parent
WORKER_PATH = SERVER_ROOT / "browser_worker.py"
IDLE_TIMEOUT_SECONDS = float(os.getenv("ASLM_BROWSER_WORKER_IDLE_TIMEOUT", "30"))
RESTORABLE_TOOLS = {
    "browser_snapshot",
    "browser_screenshot",
    "browser_scroll",
    "browser_key",
    "browser_wait_for_user",
}
REF_DEPENDENT_TOOLS = {
    "browser_click",
    "browser_text",
}


def _json_safe_context(context: dict[str, Any] | None) -> dict[str, Any]:
    safe_context = {
        "module_dir": str(PROJECT_ROOT),
        "project_dir": str(PROJECT_ROOT),
        **(context or {}),
    }
    safe_context.pop("mcp_session", None)
    return safe_context


class BrowserProcessManager:
    """Own the isolated browser worker process and its idle lifecycle."""

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._idle_handle: asyncio.TimerHandle | None = None
        self._last_url: str = ""
        self._session_keepalive_failed = False

    def _cancel_idle_timer(self) -> None:
        if self._idle_handle is not None:
            self._idle_handle.cancel()
            self._idle_handle = None

    def _schedule_idle_timer(self) -> None:
        self._cancel_idle_timer()
        loop = asyncio.get_running_loop()
        self._idle_handle = loop.call_later(
            IDLE_TIMEOUT_SECONDS,
            lambda: asyncio.create_task(self.shutdown(reason="idle-timeout")),
        )

    async def _ensure_process(self) -> asyncio.subprocess.Process:
        if self._process is not None and self._process.returncode is None:
            return self._process

        env = os.environ.copy()
        env["ASLM_BROWSER_AGENT_WORKER"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        self._process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(WORKER_PATH),
            cwd=str(PROJECT_ROOT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
            env=env,
            limit=32 * 1024 * 1024,
        )
        append_browser_portal_debug_event(
            {"module_dir": str(PROJECT_ROOT), "project_dir": str(PROJECT_ROOT)},
            "browser_worker_process_started",
            pid=self._process.pid,
            worker_path=str(WORKER_PATH),
            idle_timeout_seconds=IDLE_TIMEOUT_SECONDS,
        )
        return self._process

    async def _read_response(
        self,
        process: asyncio.subprocess.Process,
        request_id: str,
        *,
        context: dict[str, Any] | None,
        session: Any,
        interval: float,
        message: str,
    ) -> dict[str, Any]:
        assert process.stdout is not None
        while True:
            try:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=interval)
            except asyncio.TimeoutError:
                append_browser_portal_debug_event(
                    context,
                    "browser_worker_read_timeout_keepalive",
                    pid=process.pid,
                    request_id=request_id,
                    interval=interval,
                    message=message,
                    returncode=process.returncode,
                    session_present=session is not None,
                    keepalive_failed=self._session_keepalive_failed,
                )
                if session is not None and not self._session_keepalive_failed:
                    try:
                        send_log_message = getattr(session, "send_log_message", None)
                        if send_log_message is not None:
                            await send_log_message(level="debug", data=message, logger="browser-agent")
                    except BaseException:
                        self._session_keepalive_failed = True
                continue

            if not line:
                append_browser_portal_debug_event(
                    context,
                    "browser_worker_stdout_closed",
                    pid=process.pid,
                    request_id=request_id,
                    returncode=process.returncode,
                )
                return {
                    "ok": False,
                    "error": f"browser worker exited with code {process.returncode}",
                }

            try:
                payload = json.loads(line.decode("utf-8"))
            except ValueError:
                append_browser_portal_debug_event(
                    context,
                    "browser_worker_invalid_json_response",
                    pid=process.pid,
                    request_id=request_id,
                    line_preview=line.decode("utf-8", errors="replace")[:500],
                )
                continue

            if payload.get("id") == request_id:
                append_browser_portal_debug_event(
                    context,
                    "browser_worker_response_received",
                    pid=process.pid,
                    request_id=request_id,
                    ok=payload.get("ok"),
                    error=payload.get("error"),
                    result_type=type(payload.get("result")).__name__,
                )
                return payload

    def _remember_result(self, result: Any) -> None:
        url = ""
        if isinstance(result, dict):
            frame = result.get("frame") if isinstance(result.get("frame"), dict) else {}
            ui = result.get("ui") if isinstance(result.get("ui"), dict) else {}
            ui_frame = ui.get("frame") if isinstance(ui.get("frame"), dict) else {}
            url = str(result.get("url") or frame.get("url") or ui_frame.get("url") or "").strip()
        if url and url not in {"about:blank", ""}:
            self._last_url = url

    async def _discard_process_locked(
        self,
        process: asyncio.subprocess.Process,
        *,
        context: dict[str, Any] | None,
        reason: str,
    ) -> None:
        """Forget and stop a worker process whose pipes are no longer usable."""

        if self._process is process:
            self._process = None
        append_browser_portal_debug_event(
            context,
            "browser_worker_process_discarded",
            pid=process.pid,
            reason=reason,
            returncode=process.returncode,
        )
        if process.returncode is not None:
            return
        try:
            process.kill()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except Exception:
            pass

    def _worker_response_is_retryable(self, response: dict[str, Any]) -> bool:
        if response.get("ok"):
            return False
        error = str(response.get("error") or "").lower()
        return any(
            marker in error
            for marker in (
                "browser worker is unavailable",
                "browser worker stdin is unavailable",
                "browser worker exited",
                "broken pipe",
                "connection lost",
            )
        )

    async def _send_tool_request_locked(
        self,
        process: asyncio.subprocess.Process,
        tool_name: str,
        arguments: dict[str, Any] | None,
        context: dict[str, Any] | None,
        *,
        session: Any,
        interval: float,
        message: str,
    ) -> dict[str, Any]:
        if process.stdin is None:
            await self._discard_process_locked(
                process,
                context=context,
                reason="stdin-unavailable",
            )
            return {"ok": False, "error": "browser worker stdin is unavailable."}

        request_id = uuid.uuid4().hex
        request = {
            "id": request_id,
            "tool": tool_name,
            "arguments": arguments or {},
            "context": _json_safe_context(context),
        }
        append_browser_portal_debug_event(
            context,
            "browser_worker_request_send_start",
            pid=process.pid,
            request_id=request_id,
            tool_name=tool_name,
            arguments=arguments or {},
            process_returncode=process.returncode,
            stdin_is_none=process.stdin is None,
            stdout_is_none=process.stdout is None,
        )
        try:
            process.stdin.write((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
            await process.stdin.drain()
            append_browser_portal_debug_event(
                context,
                "browser_worker_request_send_done",
                pid=process.pid,
                request_id=request_id,
                tool_name=tool_name,
                process_returncode=process.returncode,
            )
        except (BrokenPipeError, ConnectionError, OSError, AttributeError, RuntimeError) as exc:
            append_browser_portal_debug_event(
                context,
                "browser_worker_request_send_error",
                pid=process.pid,
                request_id=request_id,
                tool_name=tool_name,
                error_type=type(exc).__name__,
                error=str(exc),
                process_returncode=process.returncode,
                stdin_transport=repr(getattr(process.stdin, "_transport", None)) if process.stdin is not None else None,
            )
            await self._discard_process_locked(
                process,
                context=context,
                reason=f"send-error:{type(exc).__name__}",
            )
            return {"ok": False, "error": f"browser worker is unavailable: {exc}"}

        return await self._read_response(
            process,
            request_id,
            context=context,
            session=session,
            interval=interval,
            message=message,
        )

    def _restored_refs_message(self, result: Any) -> Any:
        note = (
            "Browser process was restored after idle timeout. The previous browser refs are no longer valid. "
            "Use the fresh refs in this snapshot and retry the intended action."
        )
        if isinstance(result, dict) and isinstance(result.get("model_context"), str):
            restored = dict(result)
            restored["model_context"] = f"{note}\n\n{result['model_context']}"
            if isinstance(restored.get("ui"), dict):
                restored["ui"] = dict(restored["ui"])
                restored["ui"]["status"] = "done"
            return restored
        if isinstance(result, str):
            return f"{note}\n\n{result}"
        return result

    async def _restore_after_worker_restart_locked(
        self,
        process: asyncio.subprocess.Process,
        tool_name: str,
        context: dict[str, Any] | None,
        *,
        session: Any,
        interval: float,
    ) -> Any | None:
        if tool_name == "browser_navigate":
            return None

        if not self._last_url:
            return (
                "Error: browser worker restarted, but no previous page is available to restore. "
                "Call browser_navigate(url) first."
            )

        restore_response = await self._send_tool_request_locked(
            process,
            "browser_navigate",
            {"url": self._last_url},
            context,
            session=session,
            interval=interval,
            message=f"restoring browser page {self._last_url}...",
        )
        if not restore_response.get("ok"):
            return f"Error: browser restore failed: {restore_response.get('error') or 'unknown error'}"

        self._remember_result(restore_response.get("result"))
        if tool_name in REF_DEPENDENT_TOOLS or tool_name not in RESTORABLE_TOOLS:
            return self._restored_refs_message(restore_response.get("result"))
        return None

    async def call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        context: dict[str, Any] | None,
        *,
        session: Any = None,
        interval: float = 3.0,
        message: str = "working...",
    ) -> Any:
        async with self._lock:
            self._cancel_idle_timer()
            active_process = self._process is not None and self._process.returncode is None
            process = await self._ensure_process()
            append_browser_portal_debug_event(
                context,
                "browser_process_call_start",
                tool_name=tool_name,
                active_process=active_process,
                pid=process.pid,
                process_returncode=process.returncode,
                last_url=self._last_url,
            )

            if not active_process and tool_name != "browser_navigate" and self._last_url:
                restore_response = await self._send_tool_request_locked(
                    process,
                    "browser_navigate",
                    {"url": self._last_url},
                    context,
                    session=session,
                    interval=interval,
                    message=f"restoring browser page {self._last_url}...",
                )
                if restore_response.get("ok"):
                    self._remember_result(restore_response.get("result"))
                    if tool_name in REF_DEPENDENT_TOOLS:
                        if self._process is process and process.returncode is None:
                            self._schedule_idle_timer()
                        return self._restored_refs_message(restore_response.get("result"))
                    if tool_name not in RESTORABLE_TOOLS:
                        if self._process is process and process.returncode is None:
                            self._schedule_idle_timer()
                        return self._restored_refs_message(restore_response.get("result"))
                else:
                    return f"Error: browser restore failed: {restore_response.get('error') or 'unknown error'}"
            elif not active_process and tool_name != "browser_navigate":
                return (
                    "Error: browser is not open yet and there is no page to restore. "
                    "Call browser_navigate(url) first."
                )

            response = await self._send_tool_request_locked(
                process,
                tool_name,
                arguments,
                context,
                session=session,
                interval=interval,
                message=message,
            )
            if self._worker_response_is_retryable(response):
                append_browser_portal_debug_event(
                    context,
                    "browser_process_call_retry_after_worker_failure",
                    tool_name=tool_name,
                    previous_pid=process.pid,
                    error=response.get("error"),
                    last_url=self._last_url,
                )
                process = await self._ensure_process()
                restored_result = await self._restore_after_worker_restart_locked(
                    process,
                    tool_name,
                    context,
                    session=session,
                    interval=interval,
                )
                if restored_result is not None:
                    if self._process is process and process.returncode is None:
                        self._schedule_idle_timer()
                    return restored_result
                response = await self._send_tool_request_locked(
                    process,
                    tool_name,
                    arguments,
                    context,
                    session=session,
                    interval=interval,
                    message=message,
                )
            if self._process is process and process.returncode is None:
                self._schedule_idle_timer()
            if response.get("ok"):
                result = response.get("result")
                self._remember_result(result)
                append_browser_portal_debug_event(
                    context,
                    "browser_process_call_done",
                    tool_name=tool_name,
                    pid=process.pid,
                    last_url=self._last_url,
                    result_type=type(result).__name__,
                )
                return result
            append_browser_portal_debug_event(
                context,
                "browser_process_call_failed",
                tool_name=tool_name,
                pid=process.pid,
                error=response.get("error"),
                process_returncode=process.returncode,
            )
            return f"Error: browser worker failed: {response.get('error') or 'unknown error'}"

    async def shutdown(self, *, reason: str = "shutdown") -> None:
        async with self._lock:
            self._cancel_idle_timer()
            process = self._process
            if process is None:
                return
            self._process = None
            append_browser_portal_debug_event(
                None,
                "browser_worker_shutdown_start",
                pid=process.pid,
                reason=reason,
                returncode=process.returncode,
            )

            if process.returncode is not None:
                return

            request_id = uuid.uuid4().hex
            graceful = False
            try:
                if process.stdin is not None:
                    process.stdin.write(
                        (json.dumps({"id": request_id, "command": "shutdown", "reason": reason}) + "\n").encode(
                            "utf-8"
                        )
                    )
                    await process.stdin.drain()
                if process.stdout is not None:
                    response = await asyncio.wait_for(process.stdout.readline(), timeout=5)
                    graceful = bool(response)
            except Exception:
                graceful = False

            if graceful:
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                    return
                except Exception:
                    pass

            try:
                process.kill()
            except ProcessLookupError:
                return
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except Exception:
                pass


browser_process_manager = BrowserProcessManager()
