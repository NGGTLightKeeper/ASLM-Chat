# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.extract.page_normalizer import normalize_page
from core.fetch.camoufox_fetcher import fetch_with_camoufox, is_camoufox_available

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - optional dependency in script mode
    BeautifulSoup = None  # type: ignore[assignment]


_JSON_KEY_HINTS: tuple[str, ...] = (
    '"widgets"',
    '"collections"',
    '"meta"',
    '"productid"',
    '"skuid"',
    '"offerid"',
    '"businessid"',
    '"showuid"',
    '"transitionid"',
    '"cartbutton"',
    '"togglewishlist"',
    '"addtocartbutton"',
    '"ecommerce"',
    '"pendingcartitem"',
    '"splitpayments"',
    '"pricedetailsaction"',
    '"cpaurl"',
)
_OPAQUE_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_-]{48,}\b")
_CAMEL_KEY_RE = re.compile(r'"[a-z]+[A-Z][A-Za-z0-9]*"\s*:')
_TRACKING_PARAM_RE = re.compile(r"([?&])(cpc|do-waremd5|ogV|clid|utm_[a-z_]+)=[^&\s]+", re.IGNORECASE)
_PRICE_HINT_RE = re.compile(r"\b\d[\d\s]{2,}(?:[.,]\d+)?\s?(?:₽|руб|rur|rub)\b", re.IGNORECASE)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


@dataclass
class ProbeStats:
    html_removed_nodes: int = 0
    markdown_removed_blocks: int = 0


# Collapse runs of whitespace to a single space.
def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# Split normalized markdown into header (before ---) and body.
def _split_markdown_document(markdown: str) -> tuple[str, str]:
    marker = "\n\n---\n\n"
    if marker not in markdown:
        return "", markdown
    head, body = markdown.split(marker, 1)
    return head + marker, body


# Extract <title> text from raw HTML.
def _extract_html_title(raw_html: str) -> str:
    match = _TITLE_RE.search(raw_html or "")
    return _normalize_ws(match.group(1)) if match else ""


# Detect captcha or access-denied pages from title/body heuristics.
def _detect_fetch_blocker(raw_html: str) -> str:
    compact = _normalize_ws(raw_html).lower()
    title = _extract_html_title(raw_html).lower()
    if "are you not a robot?" in title or "smartcaptcha" in compact or "checkcaptcha" in compact:
        return "captcha"
    if "access denied" in title or "forbidden" in title:
        return "access_denied"
    return ""


# Score how likely text is SPA/widget JSON machine noise.
def _machine_noise_score(text: str) -> float:
    compact = _normalize_ws(text)
    if not compact:
        return 0.0

    lower = compact.lower()
    length = len(compact)
    punct_ratio = sum(compact.count(ch) for ch in '{}[]":,') / max(1, length)
    key_hits = sum(1 for hint in _JSON_KEY_HINTS if hint in lower)
    opaque_hits = len(_OPAQUE_TOKEN_RE.findall(compact))
    camel_hits = len(_CAMEL_KEY_RE.findall(compact))
    colon_density = compact.count(":") / max(1, length)

    score = 0.0
    if punct_ratio >= 0.10:
        score += 1.4
    elif punct_ratio >= 0.06:
        score += 0.8

    if colon_density >= 0.025:
        score += 0.8

    score += min(key_hits * 0.7, 3.5)
    score += min(opaque_hits * 0.45, 2.0)
    score += min(camel_hits * 0.2, 1.2)

    if length >= 220 and ("{" in compact or "[" in compact):
        score += 0.5

    if compact.count('","') >= 3 or compact.count('"},{"') >= 2:
        score += 1.0

    if _PRICE_HINT_RE.search(lower):
        score -= 0.4
    if lower.startswith("рейтинг товара") or lower.startswith("rating"):
        score -= 0.5

    return score


# True when machine-noise score exceeds the removal threshold.
def _looks_like_machine_noise(text: str) -> bool:
    compact = _normalize_ws(text)
    if len(compact) < 180:
        return False
    return _machine_noise_score(compact) >= 2.0


# Remove DOM subtrees that look like widget/ecommerce machine noise.
def _prune_html_machine_nodes(raw_html: str) -> tuple[str, ProbeStats]:
    stats = ProbeStats()
    if not raw_html or BeautifulSoup is None:
        return raw_html, stats

    soup = BeautifulSoup(raw_html, "html.parser")
    for node in soup.find_all(True):
        if node.name in {"html", "body", "main", "article"}:
            continue

        attrs = " ".join(
            str(value)
            for key, value in (node.attrs or {}).items()
            if key in {"id", "class", "role", "data-testid", "data-zone-name"}
        ).lower()
        text = _normalize_ws(node.get_text(" ", strip=True))
        if not text:
            continue

        attr_hint = any(marker in attrs for marker in ("widget", "ecommerce", "wishlist", "cart", "carousel", "sticky"))
        if attr_hint and _looks_like_machine_noise(text):
            node.decompose()
            stats.html_removed_nodes += 1
            continue

        if _looks_like_machine_noise(text):
            node.decompose()
            stats.html_removed_nodes += 1

    return str(soup), stats


# Strip tracking query params from the **URL:** line in markdown headers.
def _clean_tracking_in_header(header: str) -> str:
    if not header:
        return header
    lines: list[str] = []
    for line in header.splitlines():
        if line.startswith("**URL:** "):
            value = line[len("**URL:** ") :]
            cleaned = _TRACKING_PARAM_RE.sub(lambda m: "?" if m.group(1) == "?" else "", value)
            cleaned = re.sub(r"[?&]+$", "", cleaned)
            cleaned = cleaned.replace("?&", "?")
            cleaned = re.sub(r"\?{2,}", "?", cleaned)
            line = f"**URL:** {cleaned}"
        lines.append(line)
    return "\n".join(lines)


# Yield paragraph blocks from markdown body text.
def _iter_markdown_blocks(body: str) -> Iterable[str]:
    return (block.strip() for block in re.split(r"\n\s*\n", body or ""))


# Drop noisy markdown blocks and redact long opaque tokens.
def _clean_markdown_machine_blocks(markdown: str) -> tuple[str, ProbeStats]:
    header, body = _split_markdown_document(markdown)
    stats = ProbeStats()
    kept: list[str] = []

    for block in _iter_markdown_blocks(body):
        if not block:
            continue
        if _looks_like_machine_noise(block):
            stats.markdown_removed_blocks += 1
            continue
        cleaned = _OPAQUE_TOKEN_RE.sub("[token]", block)
        kept.append(cleaned)

    cleaned_body = "\n\n".join(kept).strip()
    cleaned_header = _clean_tracking_in_header(header)
    return f"{cleaned_header}{cleaned_body}".strip(), stats


# Full pipeline: prune HTML noise, normalize, then clean markdown blocks.
def clean_spa_markdown(url: str, raw_html: str) -> tuple[str, dict[str, int]]:
    pruned_html, html_stats = _prune_html_machine_nodes(raw_html)
    markdown = normalize_page(url, pruned_html)
    cleaned_markdown, md_stats = _clean_markdown_machine_blocks(markdown)
    return cleaned_markdown, {
        "html_removed_nodes": html_stats.html_removed_nodes,
        "markdown_removed_blocks": md_stats.markdown_removed_blocks,
    }


# Fetch raw HTML via Camoufox without normalization.
async def _fetch_html(url: str, timeout: float, wait_sec: float) -> str:
    if not is_camoufox_available():
        raise RuntimeError("Camoufox is unavailable")
    result = await fetch_with_camoufox(
        url,
        timeout_sec=timeout,
        process_timeout=timeout + 20.0,
        wait_sec=wait_sec,
        warmup_count=0,
        normalize=False,
    )
    if not result.success or not result.html:
        raise RuntimeError(result.error or "Failed to fetch HTML")
    return result.html


# Probe each URL: fetch, baseline normalize, clean, and print previews.
async def _run(urls: list[str], timeout: float, wait_sec: float, out_dir: str) -> int:
    out_path = Path(out_dir) if out_dir else None
    if out_path:
        out_path.mkdir(parents=True, exist_ok=True)

    for idx, url in enumerate(urls, 1):
        print(f"\n=== URL {idx}/{len(urls)} ===")
        print(url)
        raw_html = await _fetch_html(url, timeout=timeout, wait_sec=wait_sec)
        blocker = _detect_fetch_blocker(raw_html)
        title = _extract_html_title(raw_html)
        baseline = normalize_page(url, raw_html)
        cleaned, stats = clean_spa_markdown(url, raw_html)
        print(f"fetched_title={title!r}")
        if blocker:
            print(f"warning=detected_{blocker}")
        print(f"raw_html_chars={len(raw_html)} baseline_chars={len(baseline)} cleaned_chars={len(cleaned)}")
        print(
            f"html_removed_nodes={stats['html_removed_nodes']} "
            f"markdown_removed_blocks={stats['markdown_removed_blocks']}"
        )
        print("baseline_preview:")
        print(_normalize_ws(baseline)[:320])
        print("")
        print("cleaned_preview:")
        print(_normalize_ws(cleaned)[:320])

        if out_path:
            target = out_path / f"probe_{idx}.md"
            target.write_text(cleaned, encoding="utf-8")
            print(f"saved={target}")

    return 0


# Build the SPA read/clean probe CLI argument parser.
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Temporary probe for generic anti-hydration cleaning on SPA-heavy product pages.",
    )
    parser.add_argument("urls", nargs="+", help="One or more URLs to fetch and clean.")
    parser.add_argument("--timeout", type=float, default=25.0, help="Fetch timeout in seconds.")
    parser.add_argument("--wait", type=float, default=5.0, help="Extra browser wait in seconds.")
    parser.add_argument("--out-dir", default="", help="Optional directory for cleaned markdown outputs.")
    return parser.parse_args()


# CLI entry: asyncio driver for SPA cleaning probe.
def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args.urls, timeout=args.timeout, wait_sec=args.wait, out_dir=args.out_dir)))


if __name__ == "__main__":
    main()
