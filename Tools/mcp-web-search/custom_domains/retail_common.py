from __future__ import annotations

import html
import re


def strip_html_fragment(text: str) -> str:
    clean = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    clean = re.sub(r"</p\s*>", "\n\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<[^>]+>", "", clean)
    return html.unescape(clean).strip()


def format_price_value(value: str) -> str:
    digits = re.sub(r"[^\d]", "", value or "")
    if not digits:
        return ""
    return f"{int(digits):,}".replace(",", " ")


def normalize_availability(value: str) -> str:
    text = strip_html_fragment(value or "")
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n:;,.-")
    if not text:
        return ""

    lower = text.lower()
    mapping = {
        "instock": "In stock",
        "outofstock": "Out of stock",
        "preorder": "Preorder",
        "limitedavailability": "Limited availability",
    }
    compact = re.sub(r"[^a-z]", "", lower)
    if compact in mapping:
        return mapping[compact]

    allowed_exact = {
        "в наличии": "В наличии",
        "под заказ": "Под заказ",
        "нет в наличии": "Нет в наличии",
        "РІ РЅР°Р»РёС‡РёРё": "Р’ РЅР°Р»РёС‡РёРё",
        "РїРѕРґ Р·Р°РєР°Р·": "РџРѕРґ Р·Р°РєР°Р·",
        "РЅРµС‚ РІ РЅР°Р»РёС‡РёРё": "РќРµС‚ РІ РЅР°Р»РёС‡РёРё",
        "in stock": "In stock",
        "out of stock": "Out of stock",
    }
    if lower in allowed_exact:
        return allowed_exact[lower]

    if len(text) > 40:
        return ""
    if any(ch in text for ch in ('"', "{", "}", "=", ";")):
        return ""
    if re.search(r"[A-Za-z_]{6,}", text) and "stock" not in lower:
        return ""

    return text


def prepend_retail_metadata(markdown: str, meta: dict[str, str]) -> str:
    if not markdown or not meta:
        return markdown

    lines: list[str] = []
    price = meta.get("price", "").strip()
    currency = meta.get("currency", "").strip().upper()
    availability = meta.get("availability", "").strip()
    title = meta.get("title", "").strip()
    summary = meta.get("hero_summary", "").strip()
    specs = meta.get("key_specs", "").strip()

    if title:
        lines.append(f"**Product:** {title}")

    if price:
        if currency == "RUB":
            lines.append(f"**Price:** {price} RUB")
        elif currency:
            lines.append(f"**Price:** {price} {currency}")
        else:
            lines.append(f"**Price:** {price}")
    if availability:
        lines.append(f"**Availability:** {availability}")
    if summary:
        lines.append(f"**Summary:** {summary}")
    if specs:
        lines.append(f"**Key specs:** {specs}")

    if not lines:
        return markdown

    return "\n".join(lines) + "\n\n" + markdown
