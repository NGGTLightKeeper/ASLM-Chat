# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import base64
import json
import time
import uuid
from pathlib import Path
from typing import Any

from config import DOWNLOADS_DIR

# Lazy import guard for browser module — imported only inside functions to avoid
# circular imports at module load time.
_browser_mod = None


def _get_browser_mod():
    global _browser_mod
    if _browser_mod is None:
        import browser as _b
        _browser_mod = _b
    return _browser_mod

_PORTAL_FRAME_PUBLISH_LOG_COUNTER = 0


def append_browser_portal_debug_event(
    context: dict[str, Any] | None,
    event: str,
    **fields: Any,
) -> None:
    """Browser portal debug logging is intentionally disabled."""

    return None


def _status_from_result(result: Any) -> str:
    text = str(result or "").strip().lower()
    if text.startswith("error:") or text.startswith("tool execution failed:"):
        return "failed"
    if text.startswith("blocked:"):
        return "waiting"
    return "done"


async def capture_browser_portal_frame(page: Any) -> dict[str, Any] | None:
    """Capture a small UI-only viewport frame for the chat browser portal."""

    if page is None:
        return None

    try:
        data = await page.screenshot(type="jpeg", quality=58, full_page=False)
    except Exception:
        return None

    viewport = page.viewport_size or {}
    frame: dict[str, Any] = {
        "mime": "image/jpeg",
        "preview": {
            "type": "inline_base64",
            "mime_type": "image/jpeg",
            "data_base64": base64.b64encode(data).decode("utf-8"),
        },
        "size_bytes": len(data),
        "url": getattr(page, "url", "") or "",
    }
    width = viewport.get("width") if isinstance(viewport, dict) else None
    height = viewport.get("height") if isinstance(viewport, dict) else None
    if width:
        frame["width"] = width
    if height:
        frame["height"] = height
    return frame


def browser_portal_root(context: dict[str, Any] | None = None) -> Path:
    safe_context = context or {}
    module_dir = str(safe_context.get("module_dir") or safe_context.get("project_dir") or "").strip()
    selected = safe_context.get("selected_tool_server_ids")
    sandbox_enabled = bool(safe_context.get("sandbox_enabled"))
    if isinstance(selected, list):
        sandbox_enabled = sandbox_enabled or any(str(item) == "sandbox" for item in selected)
    if module_dir:
        return Path(module_dir) / "Data" / "runtime" / "browser_portal"
    return DOWNLOADS_DIR / "browser_portal"


def browser_portal_events_dir(context: dict[str, Any] | None = None) -> Path:
    return browser_portal_root(context) / "events"


def browser_portal_state_path(context: dict[str, Any] | None = None) -> Path:
    return browser_portal_root(context) / "state.json"


def reset_browser_portal_state(context: dict[str, Any] | None, *, message: str, timeout_seconds: int) -> str:
    global _PORTAL_FRAME_PUBLISH_LOG_COUNTER
    _PORTAL_FRAME_PUBLISH_LOG_COUNTER = 0
    try:
        _get_browser_mod().reset_portal_a11y_state()
    except Exception:
        pass
    root = browser_portal_root(context)
    events_dir = browser_portal_events_dir(context)
    session_id = uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    events_dir.mkdir(parents=True, exist_ok=True)
    now = time.time()
    timeout_seconds = max(1, int(timeout_seconds))
    deadline_at = now + timeout_seconds
    for path in events_dir.glob("event_*.json"):
        try:
            path.unlink()
        except OSError:
            pass
    _write_portal_state(
        context,
        {
            "ok": True,
            "status": "waiting",
            "session_id": session_id,
            "message": message,
            "timeout_seconds": timeout_seconds,
            "started_at": now,
            "deadline_at": deadline_at,
            "version": int(time.time() * 1000),
            "updated_at": now,
        },
    )
    return session_id


def _write_portal_state(
    context: dict[str, Any] | None,
    payload: dict[str, Any],
    *,
    session_id: str | None = None,
) -> bool:
    path = browser_portal_state_path(context)
    path.parent.mkdir(parents=True, exist_ok=True)
    if session_id:
        current = read_browser_portal_state(context)
        current_session_id = str(current.get("session_id") or "")
        if current_session_id and current_session_id != session_id:
            append_browser_portal_debug_event(
                context,
                "portal_state_write_skipped_session_mismatch",
                requested_session_id=session_id,
                current_session_id=current_session_id,
                payload_status=payload.get("status"),
            )
            return False
        payload = {**payload, "session_id": session_id}
    text = json.dumps(payload, ensure_ascii=False)
    encoding = "utf-8"
    # Windows: os.replace may raise PermissionError if state.json is briefly
    # locked (AV, concurrent readers). Retry, then fall back to in-place write.
    last_exc: OSError | None = None
    for attempt in range(12):
        temp_path = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_text(text, encoding=encoding)
            temp_path.replace(path)
            return True
        except PermissionError as exc:
            last_exc = exc
            try:
                if temp_path.is_file():
                    temp_path.unlink()
            except OSError:
                pass
            time.sleep(0.012 * (attempt + 1))
        except OSError as exc:
            last_exc = exc
            try:
                if temp_path.is_file():
                    temp_path.unlink()
            except OSError:
                pass
            time.sleep(0.012 * (attempt + 1))
    try:
        path.write_text(text, encoding=encoding)
        append_browser_portal_debug_event(
            context,
            "portal_state_write_inplace_fallback",
            path=str(path),
            error=str(last_exc) if last_exc else "",
        )
        return True
    except OSError as exc:
        append_browser_portal_debug_event(
            context,
            "portal_state_write_failed",
            path=str(path),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise


def read_browser_portal_state(context: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(browser_portal_state_path(context).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "error": "No browser portal frame is available yet."}
    return payload if isinstance(payload, dict) else {"ok": False, "error": "Invalid browser portal state."}


def enqueue_browser_portal_event(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    events_dir = browser_portal_events_dir(context)
    events_dir.mkdir(parents=True, exist_ok=True)
    event_id = uuid.uuid4().hex
    event = {
        "id": event_id,
        "created_at": time.time(),
        **(payload if isinstance(payload, dict) else {}),
    }
    path = events_dir / f"event_{int(time.time() * 1000)}_{event_id}.json"
    path.write_text(json.dumps(event, ensure_ascii=False), encoding="utf-8")
    append_browser_portal_debug_event(
        context,
        "portal_event_enqueued",
        event_id=event_id,
        path=str(path),
        payload=event,
    )
    return {"ok": True, "event_id": event_id}


def _pop_browser_portal_events(
    context: dict[str, Any] | None = None,
    *,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    events = []
    events_dir = browser_portal_events_dir(context)
    events_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(events_dir.glob("event_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = None
        if isinstance(payload, dict):
            event_session_id = str(payload.get("session_id") or "")
            if session_id and event_session_id and event_session_id != session_id:
                append_browser_portal_debug_event(
                    context,
                    "portal_event_skipped_session_mismatch",
                    path=str(path),
                    requested_session_id=session_id,
                    event_session_id=event_session_id,
                    payload=payload,
                )
                continue
            try:
                path.unlink()
            except OSError:
                pass
            events.append(payload)
            append_browser_portal_debug_event(
                context,
                "portal_event_popped",
                path=str(path),
                session_id=session_id,
                payload=payload,
            )
        else:
            try:
                path.unlink()
            except OSError:
                pass
    return events


async def publish_browser_portal_frame(
    page: Any,
    context: dict[str, Any] | None = None,
    *,
    status: str = "waiting",
    message: str = "",
    timeout_seconds: int | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    frame = await capture_browser_portal_frame(page)
    a11y: dict[str, Any] | None = None
    try:
        a11y = await _get_browser_mod().capture_portal_a11y_bundle(page)
    except Exception:
        pass

    now = time.time()
    existing_state = read_browser_portal_state(context)
    existing_session_id = str(existing_state.get("session_id") or "")
    same_session = not session_id or not existing_session_id or existing_session_id == session_id
    started_at = existing_state.get("started_at") if same_session else None
    deadline_at = existing_state.get("deadline_at") if same_session else None
    if started_at is None and timeout_seconds is not None:
        started_at = now
    if deadline_at is None and timeout_seconds is not None:
        try:
            deadline_at = float(started_at if started_at is not None else now) + max(1, int(timeout_seconds))
        except (TypeError, ValueError):
            deadline_at = now + max(1, int(timeout_seconds))

    payload: dict[str, Any] = {
        "ok": True,
        "status": status,
        "frame": frame,
        "url": getattr(page, "url", "") if page is not None else "",
        "version": int(time.time() * 1000),
        "updated_at": now,
    }
    if a11y is not None:
        payload["a11y"] = a11y
    if message:
        payload["message"] = message
    if timeout_seconds is not None:
        payload["timeout_seconds"] = timeout_seconds
    if started_at is not None:
        payload["started_at"] = started_at
    if deadline_at is not None:
        payload["deadline_at"] = deadline_at
    _write_portal_state(context, payload, session_id=session_id)
    return payload


async def apply_browser_portal_events(
    page: Any,
    context: dict[str, Any] | None = None,
    *,
    session_id: str | None = None,
) -> bool:
    should_finish = False
    for event in _pop_browser_portal_events(context, session_id=session_id):
        event_type = str(event.get("type") or "").strip().lower()
        append_browser_portal_debug_event(
            context,
            "portal_event_apply_start",
            session_id=session_id,
            event_type=event_type,
            payload=event,
            page_url=getattr(page, "url", "") if page is not None else "",
        )
        if event_type == "finish":
            should_finish = True
            append_browser_portal_debug_event(
                context,
                "portal_event_apply_finish_requested",
                session_id=session_id,
                payload=event,
            )
            continue
        if page is None:
            append_browser_portal_debug_event(
                context,
                "portal_event_apply_skipped_no_page",
                session_id=session_id,
                event_type=event_type,
                payload=event,
            )
            continue
        try:
            if event_type == "click":
                viewport = page.viewport_size or {"width": 1280, "height": 800}
                browser_w = int(viewport.get("width") or 1280)
                browser_h = int(viewport.get("height") or 800)
                view_w = max(1, int(event.get("viewport_width") or browser_w))
                view_h = max(1, int(event.get("viewport_height") or browser_h))
                x = float(event.get("x") or 0) * browser_w / view_w
                y = float(event.get("y") or 0) * browser_h / view_h
                await page.mouse.click(x, y)
                await page.wait_for_timeout(120)
                append_browser_portal_debug_event(
                    context,
                    "portal_event_apply_click_done",
                    session_id=session_id,
                    x=x,
                    y=y,
                    browser_width=browser_w,
                    browser_height=browser_h,
                    view_width=view_w,
                    view_height=view_h,
                )
            elif event_type == "scroll":
                await page.mouse.wheel(float(event.get("delta_x") or 0), float(event.get("delta_y") or 0))
                await page.wait_for_timeout(80)
                append_browser_portal_debug_event(
                    context,
                    "portal_event_apply_scroll_done",
                    session_id=session_id,
                    delta_x=event.get("delta_x"),
                    delta_y=event.get("delta_y"),
                )
            elif event_type == "key":
                key = str(event.get("key") or "")
                if key:
                    await page.keyboard.press(key)
                await page.wait_for_timeout(80)
                append_browser_portal_debug_event(
                    context,
                    "portal_event_apply_key_done",
                    session_id=session_id,
                    key=key,
                )
            elif event_type == "type":
                text = str(event.get("text") or "")
                if text:
                    await page.keyboard.insert_text(text)
                await page.wait_for_timeout(80)
                append_browser_portal_debug_event(
                    context,
                    "portal_event_apply_type_done",
                    session_id=session_id,
                    text_length=len(text),
                    text_preview=text[:200],
                )
            elif event_type == "click_ref":
                ref = str(event.get("ref") or "").strip()
                if ref:
                    await _get_browser_mod()._click_by_role_and_name(ref)
                    await page.wait_for_timeout(120)
                    append_browser_portal_debug_event(
                        context,
                        "portal_event_apply_click_ref_done",
                        session_id=session_id,
                        ref=ref,
                    )
                else:
                    append_browser_portal_debug_event(
                        context,
                        "portal_event_apply_click_ref_missing",
                        session_id=session_id,
                    )
            else:
                append_browser_portal_debug_event(
                    context,
                    "portal_event_apply_unknown_type",
                    session_id=session_id,
                    event_type=event_type,
                    payload=event,
                )
        except Exception as exc:
            append_browser_portal_debug_event(
                context,
                "portal_event_apply_error",
                session_id=session_id,
                event_type=event_type,
                error_type=type(exc).__name__,
                error=str(exc),
                payload=event,
            )
            continue
    return should_finish


async def with_browser_portal_ui(
    result: Any,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    page: Any,
) -> Any:
    """Wrap a text tool result with UI metadata without changing model text."""

    if not isinstance(result, str):
        return result

    frame = await capture_browser_portal_frame(page)
    return {
        "model_context": result,
        "kind": "browser_portal",
        "tool": tool_name,
        "arguments": dict(arguments or {}),
        "status": _status_from_result(result),
        "frame": frame,
        "ui": {
            "kind": "browser_portal",
            "status": _status_from_result(result),
            "tool": tool_name,
            "arguments": dict(arguments or {}),
            "frame": frame,
        },
    }
