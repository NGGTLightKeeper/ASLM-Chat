"""Public Stack Exchange question fetcher for read_page and preview paths."""

from __future__ import annotations

import asyncio
import html
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from core.fetch.thread_pool import io_pool as _io_pool

_QUESTION_RE = re.compile(r"/questions/(\d+)(?:/|$)")
_HOST_TO_SITE = {
    "stackoverflow.com": "stackoverflow",
    "superuser.com": "superuser",
    "serverfault.com": "serverfault",
    "askubuntu.com": "askubuntu",
}


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _site_from_host(host: str) -> str | None:
    if host in _HOST_TO_SITE:
        return _HOST_TO_SITE[host]
    if host.endswith(".stackexchange.com"):
        return host.split(".", 1)[0]
    return None


def stackexchange_question_id(url: str) -> str | None:
    m = _QUESTION_RE.search(urlparse(url).path)
    return m.group(1) if m else None


def is_stackexchange_question_url(url: str) -> bool:
    return _site_from_host(_host(url)) is not None and stackexchange_question_id(url) is not None


def _strip_html_fragment(fragment: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(fragment or "", "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        for pre in soup.find_all("pre"):
            code_text = pre.get_text("\n", strip=False)
            pre.replace_with("\n```text\n" + code_text.strip() + "\n```\n")
        text = soup.get_text("\n", strip=True)
        return html.unescape(text).strip()
    except Exception:
        text = re.sub(r"<br\s*/?>", "\n", fragment or "", flags=re.IGNORECASE)
        text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        return html.unescape(text).strip()


def _format_timestamp(value: object) -> str:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return ""


def _stackexchange_api_get(url: str, timeout: int) -> dict[str, Any]:
    from curl_cffi import requests as _r

    resp = _r.get(
        url,
        impersonate="chrome124",
        timeout=timeout,
        headers={
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": "Mozilla/5.0",
        },
    )
    resp.raise_for_status()
    return resp.json()


def render_stackexchange_question_markdown(
    url: str,
    question: dict[str, Any],
    answers: list[dict[str, Any]],
) -> str:
    host = _host(url)
    title = str(question.get("title") or "").strip() or "Stack Exchange Question"
    body = _strip_html_fragment(str(question.get("body") or ""))
    owner = question.get("owner") if isinstance(question.get("owner"), dict) else {}
    author = str(owner.get("display_name") or "").strip()
    created = _format_timestamp(question.get("creation_date"))
    score = question.get("score")
    tags = question.get("tags") if isinstance(question.get("tags"), list) else []

    lines = [f"# {title}", "", f"**Site:** {host}", f"**URL:** {url}"]
    if author:
        lines.append(f"**Author:** {author}")
    if created:
        lines.append(f"**Created:** {created}")
    if score is not None:
        lines.append(f"**Score:** {score}")
    if tags:
        lines.append(f"**Tags:** {', '.join(str(tag) for tag in tags if str(tag).strip())}")
    lines.extend(["", "---", ""])
    if body:
        lines.append(body)

    if answers:
        lines.extend(["", "## Top Answers", ""])
        for idx, answer in enumerate(answers, 1):
            answer_owner = answer.get("owner") if isinstance(answer.get("owner"), dict) else {}
            answer_author = str(answer_owner.get("display_name") or "").strip()
            answer_created = _format_timestamp(answer.get("creation_date"))
            answer_score = answer.get("score")
            accepted = bool(answer.get("is_accepted"))
            header = f"### Answer {idx}"
            if accepted:
                header += " [accepted]"
            lines.extend([header, ""])
            meta: list[str] = []
            if answer_author:
                meta.append(f"Author: {answer_author}")
            if answer_created:
                meta.append(f"Created: {answer_created}")
            if answer_score is not None:
                meta.append(f"Score: {answer_score}")
            if meta:
                lines.append(" | ".join(meta))
                lines.append("")
            answer_body = _strip_html_fragment(str(answer.get("body") or ""))
            if answer_body:
                lines.append(answer_body)
            lines.append("")

    return "\n".join(lines).strip()


def fetch_stackexchange_question_sync(url: str, timeout: float = 20.0, answer_limit: int = 3) -> str:
    host = _host(url)
    site = _site_from_host(host)
    qid = stackexchange_question_id(url)
    if not site or not qid:
        return f"Error: Unsupported Stack Exchange question URL: {url}"

    timeout_int = max(10, int(timeout))
    question_url = f"https://api.stackexchange.com/2.3/questions/{qid}?site={site}&filter=withbody"
    answers_url = (
        f"https://api.stackexchange.com/2.3/questions/{qid}/answers"
        f"?site={site}&filter=withbody&sort=votes"
    )

    question_payload = _stackexchange_api_get(question_url, timeout_int)
    question_items = question_payload.get("items") if isinstance(question_payload, dict) else []
    if not isinstance(question_items, list) or not question_items:
        return f"Error: Stack Exchange API returned no question data for: {url}"

    answers_payload = _stackexchange_api_get(answers_url, timeout_int)
    answer_items = answers_payload.get("items") if isinstance(answers_payload, dict) else []
    if not isinstance(answer_items, list):
        answer_items = []

    return render_stackexchange_question_markdown(
        url,
        question_items[0],
        answer_items[: max(0, int(answer_limit))],
    )


async def fetch_stackexchange_question(url: str, timeout: float = 20.0, answer_limit: int = 3) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _io_pool,
        lambda: fetch_stackexchange_question_sync(url, timeout=timeout, answer_limit=answer_limit),
    )
