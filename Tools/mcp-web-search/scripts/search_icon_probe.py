#!/usr/bin/env python3
# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Render a small HTML report showing search source icons.

The report answers: which favicon URL did web_search return, what image did
that URL actually serve, and would the ASLM UI use that favicon or its local
fallback for the source chip.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import html
import json
import mimetypes
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.web_search import run_web_search_rich


@dataclass
class IconFetch:
    ok: bool
    status: int
    content_type: str
    byte_count: int
    data_url: str
    error: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="scripts/search_icon_probe.py")
    parser.add_argument("query", help="Search query to run through web_search_rich.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum search results. Default: 10")
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-icon fetch timeout. Default: 10s")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="HTML output path. Default: tmp/search_icon_probe_<timestamp>.html",
    )
    return parser.parse_args()


def _source_uses_favicon(source: dict[str, Any]) -> bool:
    """Mirror Apps/UI/static/js/ui/messages-ui.js sourceHasExtractedPreview."""

    has_preview = "preview" in source
    has_snippet = "snippet" in source
    if not has_preview and not has_snippet:
        return True
    preview = str(source.get("preview") or "").strip()
    snippet = str(source.get("snippet") or "").strip()
    return bool(preview) and preview != snippet


def _display_domain(source: dict[str, Any]) -> str:
    return str(source.get("display_domain") or source.get("domain") or "").strip()


def _fallback_letter(source: dict[str, Any]) -> str:
    domain = _display_domain(source)
    return (domain[:1] or "?").upper()


def _fetch_icon(url: str, timeout: float) -> IconFetch:
    if not url:
        return IconFetch(False, 0, "", 0, "", "empty icon url")

    try:
        request = Request(url, headers={"User-Agent": "ASLM-Chat icon probe/1.0"})
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(128 * 1024)
            status = int(getattr(response, "status", 0) or 0)
            content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip()
            if not content_type:
                content_type = mimetypes.guess_type(url)[0] or "application/octet-stream"
            data_url = f"data:{content_type};base64,{base64.b64encode(raw).decode('ascii')}" if raw else ""
            return IconFetch(200 <= status < 400, status, content_type, len(raw), data_url, "")
    except HTTPError as exc:
        return IconFetch(False, int(exc.code or 0), "", 0, "", str(exc))
    except (OSError, URLError) as exc:
        return IconFetch(False, 0, "", 0, "", str(exc))


async def _fetch_icons(sources: list[dict[str, Any]], timeout: float) -> dict[str, IconFetch]:
    async def one(source: dict[str, Any]) -> tuple[str, IconFetch]:
        url = str(source.get("favicon_url") or "").strip()
        return url, await asyncio.to_thread(_fetch_icon, url, timeout)

    pairs = await asyncio.gather(*(one(source) for source in sources))
    return {url: fetch for url, fetch in pairs}


def _chip_html(source: dict[str, Any], icon: IconFetch, *, force_fallback: bool = False) -> str:
    domain = html.escape(_display_domain(source))
    letter = html.escape(_fallback_letter(source))
    if icon.ok and icon.data_url and not force_fallback:
        icon_html = f'<img src="{icon.data_url}" alt="">'
    else:
        icon_html = f'<span class="fallback">{letter}</span>'
    return f'<span class="chip">{icon_html}<span>{domain}</span></span>'


def _render_html(query: str, payload: dict[str, Any], icon_fetches: dict[str, IconFetch]) -> str:
    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    rows: list[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        icon_url = str(source.get("favicon_url") or "").strip()
        icon = icon_fetches.get(icon_url) or IconFetch(False, 0, "", 0, "", "not fetched")
        ui_uses_favicon = _source_uses_favicon(source)
        title = html.escape(str(source.get("title") or ""))
        url = html.escape(str(source.get("url") or ""))
        domain = html.escape(_display_domain(source))
        rank = html.escape(str(source.get("rank") or ""))
        source_id = html.escape(str(source.get("id") or ""))
        status = "favicon" if ui_uses_favicon else "fallback"
        parse_state = "parsed preview" if ui_uses_favicon else "snippet-only"
        error = html.escape(icon.error)
        icon_url_escaped = html.escape(icon_url)
        content_type = html.escape(icon.content_type)
        actual_img = (
            f'<img class="actual-icon" src="{icon.data_url}" alt="">'
            if icon.ok and icon.data_url
            else '<span class="actual-missing">no image</span>'
        )
        rows.append(
            f"""
            <tr>
              <td class="rank">{rank}</td>
              <td>
                <div class="title">{title}</div>
                <div class="muted">{domain} · {source_id}</div>
                <a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>
              </td>
              <td>{_chip_html(source, icon, force_fallback=False)}</td>
              <td>{_chip_html(source, icon, force_fallback=not ui_uses_favicon)}</td>
              <td>{actual_img}</td>
              <td>
                <div><strong>{status}</strong> in UI</div>
                <div class="muted">{parse_state}</div>
                <div class="muted">HTTP {icon.status or "?"}, {icon.byte_count} bytes, {content_type or "unknown"}</div>
                <div class="mono">{icon_url_escaped}</div>
                {f'<div class="error">{error}</div>' if error else ''}
              </td>
            </tr>
            """
        )

    payload_json = html.escape(json.dumps(payload, ensure_ascii=False, indent=2)[:40_000])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Search Icon Probe</title>
<style>
  body {{ margin: 24px; background: #0d0d0f; color: #f2f2f3; font: 14px/1.45 system-ui, sans-serif; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .muted {{ color: #a8a8ad; font-size: 12px; }}
  .mono {{ color: #9fc3ff; font: 11px/1.35 ui-monospace, Consolas, monospace; max-width: 360px; overflow-wrap: anywhere; }}
  .error {{ color: #ff9e9e; font-size: 12px; max-width: 360px; overflow-wrap: anywhere; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 18px; }}
  th, td {{ border-top: 1px solid rgba(255,255,255,.12); padding: 10px; vertical-align: middle; text-align: left; }}
  th {{ color: #c8c8cc; font-size: 12px; font-weight: 700; }}
  a {{ color: #70a7ff; text-decoration: none; }}
  .rank {{ color: #aaa; width: 36px; }}
  .title {{ font-weight: 700; max-width: 520px; }}
  .chip {{ height: 28px; display: inline-flex; align-items: center; gap: 6px; padding: 0 10px; border-radius: 999px; background: rgba(255,255,255,.08); font-weight: 700; }}
  .chip img, .chip .fallback, .actual-icon {{ width: 16px; height: 16px; border-radius: 50%; object-fit: cover; }}
  .chip .fallback {{ display: inline-flex; align-items: center; justify-content: center; background: rgba(255,255,255,.14); color: #d4d4d8; font-size: 10px; }}
  .actual-icon {{ width: 24px; height: 24px; background: #202024; }}
  .actual-missing {{ color: #aaa; font-size: 12px; }}
  details {{ margin-top: 20px; }}
  pre {{ white-space: pre-wrap; background: rgba(255,255,255,.05); padding: 12px; border-radius: 8px; max-height: 420px; overflow: auto; }}
</style>
</head>
<body>
<h1>Search Icon Probe</h1>
<div class="muted">Query: {html.escape(query)}</div>
<table>
<thead>
<tr>
  <th>#</th>
  <th>Source</th>
  <th>Raw favicon chip</th>
  <th>ASLM UI chip</th>
  <th>Fetched image</th>
  <th>Diagnostics</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
<details>
<summary>Raw rich search payload</summary>
<pre>{payload_json}</pre>
</details>
</body>
</html>
"""


async def main() -> int:
    args = _parse_args()
    payload = await run_web_search_rich(args.query, max_results=max(1, args.limit))
    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    icon_fetches = await _fetch_icons([source for source in sources if isinstance(source, dict)], args.timeout)
    output = args.output
    if output is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = ROOT / "tmp" / f"search_icon_probe_{stamp}.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_render_html(args.query, payload, icon_fetches), encoding="utf-8")
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
