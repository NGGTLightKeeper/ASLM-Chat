# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""import_web_file tool — download a URL into the session sandbox workspace."""

from __future__ import annotations

import logging

from services.deep_research.models import ResearchSession

logger = logging.getLogger("services.deep_research.tools.import_web_file")


async def run_agent_import_web_file(
    session: ResearchSession,
    *,
    url: str,
    filename: str = "",
) -> str:
    sandbox = getattr(session, "sandbox", None)
    if sandbox is None or not getattr(sandbox, "running", False):
        return "import_web_file is only available in overdrive mode (sandbox not running)."

    settings = getattr(session, "overdrive_settings", None)
    max_size_mb = int(getattr(settings, "import_file_max_size_mb", 100)) if settings else 100
    timeout_sec = int(getattr(settings, "import_file_timeout_sec", 120)) if settings else 120

    if not url.strip():
        return "import_web_file: url is required."

    result = await sandbox.download_file(
        url,
        filename=filename.strip() or None,
        timeout_sec=timeout_sec,
        max_size_mb=max_size_mb,
    )
    session.import_file_calls += 1  # count all attempts, consistent with read_page/python

    if not result.ok:
        logger.warning("import_web_file failed: url=%s error=%s", url, result.error)
        return f"import_web_file failed: {result.error or 'unknown error'}"

    logger.info(
        "import_web_file ok: url=%s path=%s size=%d bytes elapsed_ms=%d",
        url, result.path, result.size_bytes, result.elapsed_ms,
    )
    return (
        f"File downloaded to sandbox workspace.\n"
        f"Path: {result.path}\n"
        f"Size: {result.size_bytes:,} bytes\n"
        f"Elapsed: {result.elapsed_ms} ms\n"
        f"Use `python` action to read, parse, or analyze this file at {result.path}"
    )
