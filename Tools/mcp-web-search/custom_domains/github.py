# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import asyncio
import base64
import os
import time
from typing import Any
from urllib.parse import quote, urlparse

from core.fetch.constants import DEFAULT_UA as _UA
from core.fetch.thread_pool import io_pool as _io_pool


# Normalize URL host (strip www./m. prefixes).
def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")


# True when URL targets github.com.
def is_github_url(url: str) -> bool:
    return _host(url) == "github.com"


# Parse owner, repo, and remaining path segments from a GitHub URL.
def _repo_parts(url: str) -> tuple[str, str, list[str]] | None:
    parsed = urlparse(url)
    if _host(url) != "github.com":
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if owner in {"features", "marketplace", "orgs", "topics", "trending"}:
        return None
    return owner, repo.removesuffix(".git"), parts[2:]


# Build GitHub REST API headers, optionally with GITHUB_TOKEN / GH_TOKEN.
def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": _UA,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# Synchronous GET returning parsed JSON from the GitHub API.
def _api_get_json(url: str, timeout: float) -> Any:
    import httpx

    resp = httpx.get(url, headers=_github_headers(), timeout=timeout, follow_redirects=False)
    resp.raise_for_status()
    return resp.json()


# Decode base64 contents field from a GitHub contents API response.
def _decode_content_payload(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    if data.get("encoding") != "base64":
        return ""
    raw = str(data.get("content") or "")
    if not raw:
        return ""
    return base64.b64decode(raw).decode("utf-8", errors="replace")


# Format repository metadata and README as markdown.
def _format_repo(repo: dict[str, Any], readme: str, url: str) -> str:
    full_name = str(repo.get("full_name") or "").strip()
    description = str(repo.get("description") or "").strip()
    lines = [f"# {full_name or url}", f"URL: {url}"]
    if description:
        lines.append(f"Description: {description}")

    meta: list[str] = []
    for label, key in (
        ("Default branch", "default_branch"),
        ("Language", "language"),
        ("Stars", "stargazers_count"),
        ("Forks", "forks_count"),
        ("Open issues", "open_issues_count"),
        ("Updated", "updated_at"),
    ):
        value = repo.get(key)
        if value not in (None, ""):
            meta.append(f"{label}: {value}")
    license_info = repo.get("license") if isinstance(repo.get("license"), dict) else {}
    if license_info.get("spdx_id"):
        meta.append(f"License: {license_info['spdx_id']}")
    topics = repo.get("topics") if isinstance(repo.get("topics"), list) else []
    if topics:
        meta.append("Topics: " + ", ".join(str(topic) for topic in topics[:20]))
    if meta:
        lines.append("")
        lines.extend(meta)

    if readme.strip():
        lines.append("")
        lines.append("## README")
        lines.append(readme.strip())
    return "\n".join(lines).strip()


# Format issue metadata, body, and comments as markdown.
def _format_issue(issue: dict[str, Any], comments: list[Any], url: str) -> str:
    title = str(issue.get("title") or url).strip()
    user = issue.get("user") if isinstance(issue.get("user"), dict) else {}
    lines = [f"# {title}", f"URL: {url}"]
    for label, key in (
        ("State", "state"),
        ("Author", "login"),
        ("Created", "created_at"),
        ("Updated", "updated_at"),
    ):
        value = user.get(key) if key == "login" else issue.get(key)
        if value:
            lines.append(f"{label}: {value}")
    body = str(issue.get("body") or "").strip()
    if body:
        lines.append("")
        lines.append(body)

    clean_comments = [comment for comment in comments if isinstance(comment, dict)]
    if clean_comments:
        lines.append("")
        lines.append("## Comments")
        for comment in clean_comments[:20]:
            author = comment.get("user") if isinstance(comment.get("user"), dict) else {}
            login = str(author.get("login") or "?")
            text = str(comment.get("body") or "").strip()
            if text:
                lines.append("")
                lines.append(f"### {login}")
                lines.append(text)
    return "\n".join(lines).strip()


# Format directory listing from GitHub contents/tree API as markdown.
def _format_tree(items: list[Any], owner: str, repo: str, ref: str, path: str, url: str) -> str:
    title_path = path or "."
    lines = [f"# {owner}/{repo}: {title_path}", f"URL: {url}", f"Ref: {ref}", ""]
    for item in items[:100]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "file")
        name = str(item.get("name") or "")
        size = item.get("size")
        suffix = f" ({size} bytes)" if kind == "file" and isinstance(size, int) else ""
        lines.append(f"- [{kind}] {name}{suffix}")
    return "\n".join(lines).strip()


# Fetch repo, issue, blob, or tree via GitHub API and return formatted markdown.
#
# The whole body below runs SYNCHRONOUSLY inside one shared-io_pool worker thread (see
# run_in_executor at the bottom). That matters: `_parse_one` wraps this call in
# `asyncio.timeout(profile.parse_timeout)`, but asyncio cancellation only stops AWAITING
# the executor future — it cannot stop a thread already blocked inside httpx.get(). A repo
# page can need up to 3 SEQUENTIAL API calls (repo, then readme/blob/tree); giving each one
# a fresh `timeout` would let the whole handler run to 2-3x the caller's real budget while
# every asyncio-side deadline above it already gave up — a hung/slow GitHub response then
# occupies the worker thread indefinitely, which is exactly the executor-exhaustion failure
# mode (see TODO.md's known-bugs backlog). A single monotonic deadline, decremented across
# calls, is the only thing that actually bounds this to the caller's declared budget.
async def fetch_github_page(url: str, timeout: float = 20.0) -> str:
    parsed = _repo_parts(url)
    if not parsed:
        return f"Error: Unsupported GitHub URL: {url}"
    owner, repo, rest = parsed
    owner_q = quote(owner, safe="")
    repo_q = quote(repo, safe="")
    deadline = time.monotonic() + max(3.0, float(timeout))

    # Seconds left before the caller's own budget is spent; never negative/zero so a
    # trailing httpx call still gets a moment to fail cleanly instead of timeout=0 raising.
    def _remaining() -> float:
        return max(0.5, deadline - time.monotonic())

    # Blocking API work run on the shared I/O thread pool.
    def _sync() -> str:
        api_root = f"https://api.github.com/repos/{owner_q}/{repo_q}"
        try:
            repo_data = _api_get_json(api_root, _remaining())
        except Exception as exc:
            return f"Error: GitHub API repo fetch failed for {url}: {exc}"

        if not rest:
            readme = ""
            if time.monotonic() < deadline:
                try:
                    readme_data = _api_get_json(f"{api_root}/readme", _remaining())
                    readme = _decode_content_payload(readme_data)
                except Exception:
                    readme = ""
            return _format_repo(repo_data, readme, url)

        kind = rest[0]
        if kind in {"issues", "pull"} and len(rest) >= 2 and rest[1].isdigit():
            number = rest[1]
            try:
                issue = _api_get_json(f"{api_root}/issues/{number}", _remaining())
                comments = _api_get_json(f"{api_root}/issues/{number}/comments?per_page=20", _remaining())
            except Exception as exc:
                return f"Error: GitHub API issue fetch failed for {url}: {exc}"
            return _format_issue(issue, comments if isinstance(comments, list) else [], url)

        if kind in {"blob", "tree"} and len(rest) >= 2:
            ref = rest[1]
            path = "/".join(rest[2:])
            path_q = quote(path, safe="/")
            if kind == "blob":
                raw_url = (
                    f"https://raw.githubusercontent.com/{quote(owner, safe='')}/"
                    f"{quote(repo, safe='')}/{quote(ref, safe='')}/{path_q}"
                )
                try:
                    import httpx

                    resp = httpx.get(
                        raw_url,
                        headers={"User-Agent": _UA},
                        timeout=_remaining(),
                        follow_redirects=True,
                    )
                    resp.raise_for_status()
                    text = resp.text
                    return f"# {owner}/{repo}: {path}\nURL: {url}\nRef: {ref}\n\n{text}".strip()
                except Exception:
                    if time.monotonic() >= deadline:
                        return f"Error: GitHub raw fetch timed out for {url}"
                    try:
                        data = _api_get_json(f"{api_root}/contents/{path_q}?ref={quote(ref, safe='')}", _remaining())
                        text = _decode_content_payload(data)
                        if text:
                            return f"# {owner}/{repo}: {path}\nURL: {url}\nRef: {ref}\n\n{text}".strip()
                    except Exception as exc:
                        return f"Error: GitHub API blob fetch failed for {url}: {exc}"
            else:
                try:
                    contents_url = f"{api_root}/contents/{path_q}?ref={quote(ref, safe='')}" if path else f"{api_root}/contents?ref={quote(ref, safe='')}"
                    data = _api_get_json(contents_url, _remaining())
                    if isinstance(data, list):
                        return _format_tree(data, owner, repo, ref, path, url)
                except Exception as exc:
                    return f"Error: GitHub API tree fetch failed for {url}: {exc}"

        return _format_repo(repo_data, "", url)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_io_pool, _sync)


from custom_domains.base import FetchContext, PageResult


# Unified handler: fetch a GitHub page via the REST API and return budgeted markdown.
class GitHubHandler:
    name = "github"
    fallback_to_generic = False

    # True when the URL targets github.com.
    def matches(self, url: str) -> bool:
        return is_github_url(url)

    # Fetch via GitHub API; mark for read_page's budget pass like the legacy path did.
    async def read(self, url: str, ctx: FetchContext) -> PageResult:
        markdown = await fetch_github_page(url, timeout=ctx.timeout)
        ok = not markdown.lstrip().lower().startswith("error:")
        return PageResult(
            markdown=markdown,
            ok=ok,
            method="github_api",
            apply_budget=True,
            error="" if ok else markdown,
        )


HANDLER = GitHubHandler()
