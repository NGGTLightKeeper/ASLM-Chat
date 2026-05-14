from __future__ import annotations

import json
import re

_PAYLOAD_RE = re.compile(
    r"<script[^>]*>\s*self\.__next_f\.push\(\[1,\s*(\"(?:\\.|[^\"\\])*\")\]\)\s*</script>",
    re.IGNORECASE | re.DOTALL,
)
_LINE_RE = re.compile(r"^([0-9a-f]+):(.*)$", re.IGNORECASE)
_REF_RE = re.compile(r"^\$L([0-9a-f]+)$", re.IGNORECASE)

_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_INLINE_TAGS = {"a", "b", "code", "em", "i", "small", "span", "strong", "sub", "sup"}
_SKIP_TAGS = {"body", "head", "html", "link", "meta", "script", "style", "template", "title"}


def extract_nextjs_rsc_text(raw_html: str) -> str:
    """Extract structured text from Next.js RSC flight payloads embedded in HTML."""

    records = _parse_rsc_records(raw_html)
    if not records:
        return ""

    blocks: list[str] = []
    for record_id, node in records.items():
        if not _is_content_root(node):
            continue
        rendered = _render_node(node, records, seen={record_id})
        for block in rendered:
            clean = _clean_block(block)
            if clean:
                blocks.append(clean)

    deduped: list[str] = []
    seen_blocks: set[str] = set()
    for block in blocks:
        if block in seen_blocks:
            continue
        seen_blocks.add(block)
        deduped.append(block)
    return "\n\n".join(deduped)


def _parse_rsc_records(raw_html: str) -> dict[str, object]:
    chunks: list[str] = []
    for match in _PAYLOAD_RE.finditer(raw_html or ""):
        try:
            chunks.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            continue

    if not chunks:
        return {}

    records: dict[str, object] = {}
    for line in "".join(chunks).splitlines():
        match = _LINE_RE.match(line.strip())
        if not match:
            continue
        record_id, value = match.groups()
        value = value.strip()
        if not value or value[0] not in '[{"':
            continue
        try:
            records[record_id.lower()] = json.loads(value)
        except json.JSONDecodeError:
            continue
    return records


def _is_content_root(node: object) -> bool:
    if not _is_element(node):
        return False

    tag = _tag_name(node)
    props = _props(node)
    class_name = str(props.get("className") or "")

    if tag in _HEADING_TAGS:
        return True
    if tag in {"ol", "p", "table", "tr", "ul"}:
        return True
    if tag == "div" and "full-width-table" in class_name:
        return True
    if isinstance(tag, str) and tag.startswith("$L") and props.get("baseId"):
        return True
    return False


def _render_node(node: object, records: dict[str, object], seen: set[str]) -> list[str]:
    if isinstance(node, str):
        resolved = _resolve_ref(node, records, seen)
        if resolved is not None:
            return _render_node(resolved, records, seen)
        return []

    if isinstance(node, dict):
        if "children" in node:
            return _render_node(node["children"], records, seen)
        return []

    if not isinstance(node, list):
        return []

    if not _is_element(node):
        blocks: list[str] = []
        for child in node:
            blocks.extend(_render_node(child, records, seen))
        return blocks

    tag = _tag_name(node)
    if tag in _SKIP_TAGS:
        return []

    props = _props(node)
    children = props.get("children")

    if tag in _HEADING_TAGS or (isinstance(tag, str) and tag.startswith("$L") and props.get("baseId")):
        text = _inline_text(children, records, seen)
        return [f"## {text}"] if text else []

    if tag == "p":
        text = _inline_text(children, records, seen)
        return [text] if text else []

    if tag in {"ul", "ol"}:
        return _render_list(children, records, seen)

    if tag in {"table", "tr"} or (tag == "div" and "full-width-table" in str(props.get("className") or "")):
        return _render_table_like(node if tag == "tr" else children, records, seen)

    return []


def _render_list(node: object, records: dict[str, object], seen: set[str]) -> list[str]:
    items = _find_list_items(node, records, seen)
    return [f"- {item}" for item in items if item]


def _find_list_items(node: object, records: dict[str, object], seen: set[str]) -> list[str]:
    resolved = _resolve_if_ref(node, records, seen)
    if resolved is not None:
        return _find_list_items(resolved, records, seen)

    if isinstance(node, dict):
        return _find_list_items(node.get("children"), records, seen)

    if not isinstance(node, list):
        return []

    if _is_element(node):
        tag = _tag_name(node)
        props = _props(node)
        if tag == "li":
            text = _inline_text(props.get("children"), records, seen)
            return [text] if text else []
        return _find_list_items(props.get("children"), records, seen)

    items: list[str] = []
    for child in node:
        items.extend(_find_list_items(child, records, seen))
    return items


def _render_table_like(node: object, records: dict[str, object], seen: set[str]) -> list[str]:
    rows = _find_table_rows(node, records, seen)
    return [" | ".join(row) for row in rows if row]


def _find_table_rows(node: object, records: dict[str, object], seen: set[str]) -> list[list[str]]:
    resolved = _resolve_if_ref(node, records, seen)
    if resolved is not None:
        return _find_table_rows(resolved, records, seen)

    if isinstance(node, dict):
        return _find_table_rows(node.get("children"), records, seen)

    if not isinstance(node, list):
        return []

    if _is_element(node):
        tag = _tag_name(node)
        props = _props(node)
        if tag == "tr":
            cells = _find_row_cells(props.get("children"), records, seen)
            return [cells] if cells else []
        return _find_table_rows(props.get("children"), records, seen)

    rows: list[list[str]] = []
    for child in node:
        rows.extend(_find_table_rows(child, records, seen))
    return rows


def _find_row_cells(node: object, records: dict[str, object], seen: set[str]) -> list[str]:
    resolved = _resolve_if_ref(node, records, seen)
    if resolved is not None:
        return _find_row_cells(resolved, records, seen)

    if isinstance(node, dict):
        return _find_row_cells(node.get("children"), records, seen)

    if not isinstance(node, list):
        return []

    if _is_element(node):
        tag = _tag_name(node)
        props = _props(node)
        if tag in {"td", "th"}:
            text = _inline_text(props.get("children"), records, seen)
            return [text] if text else []
        return _find_row_cells(props.get("children"), records, seen)

    cells: list[str] = []
    for child in node:
        cells.extend(_find_row_cells(child, records, seen))
    return cells


def _inline_text(node: object, records: dict[str, object], seen: set[str]) -> str:
    resolved = _resolve_if_ref(node, records, seen)
    if resolved is not None:
        return _inline_text(resolved, records, seen)

    if isinstance(node, str):
        return _clean_inline_text(node)

    if isinstance(node, dict):
        return _inline_text(node.get("children"), records, seen)

    if not isinstance(node, list):
        return ""

    if _is_element(node):
        tag = _tag_name(node)
        if tag in _SKIP_TAGS:
            return ""
        props = _props(node)
        if tag == "br":
            return "\n"
        if tag in _HEADING_TAGS | _INLINE_TAGS | {"li", "p", "td", "th"} or (
            isinstance(tag, str) and tag.startswith("$L")
        ):
            return _inline_text(props.get("children"), records, seen)
        return ""

    parts = [_inline_text(child, records, seen) for child in node]
    return _join_inline(parts)


def _clean_inline_text(text: str) -> str:
    if not text:
        return ""
    if _REF_RE.match(text) or text in {"$null", "$undefined"} or text.startswith("$@") or text.startswith("$S"):
        return ""
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()


def _clean_block(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _join_inline(parts: list[str]) -> str:
    merged = " ".join(part for part in parts if part and part != "\n")
    merged = re.sub(r"\s+", " ", merged)
    return merged.strip()


def _resolve_if_ref(node: object, records: dict[str, object], seen: set[str]) -> object | None:
    if isinstance(node, str):
        return _resolve_ref(node, records, seen)
    return None


def _resolve_ref(value: str, records: dict[str, object], seen: set[str]) -> object | None:
    match = _REF_RE.match(value)
    if not match:
        return None
    record_id = match.group(1).lower()
    if record_id in seen:
        return None
    target = records.get(record_id)
    if target is None:
        return None
    seen.add(record_id)
    return target


def _is_element(node: object) -> bool:
    return isinstance(node, list) and len(node) >= 4 and node[0] == "$"


def _tag_name(node: list[object]) -> str:
    tag = node[1]
    return tag if isinstance(tag, str) else ""


def _props(node: list[object]) -> dict[str, object]:
    props = node[3]
    return props if isinstance(props, dict) else {}
