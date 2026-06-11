# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

from custom_domains.retail_common import format_price_value, normalize_availability, strip_html_fragment


# Trim and cap a single DNS-shop spec line extracted from HTML.
def _clean_dns_spec_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip(" \t\r\n,;|")
    return cleaned[:120]


# Point product URLs at the characteristics subpage for richer read_page content.
def rewrite_read_page_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
    path = parsed.path or "/"

    if host == "dns-shop.ru" and path.startswith("/product/"):
        subpages = (
            "/product/characteristics/",
            "/product/opinion/",
            "/product/accessories/",
            "/product/service-rating/",
            "/product/similar-design/",
            "/product/analog/",
        )
        if not any(path.startswith(prefix) for prefix in subpages):
            rewritten = "/product/characteristics/" + path[len("/product/") :]
            return urlunparse(parsed._replace(path=rewritten))

    return url


# Build alternate fetch URLs (.xaml, characteristics) for a DNS-shop product page.
def dns_variant_urls(url: str) -> list[str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
    path = parsed.path or "/"
    if host != "dns-shop.ru" or not path.startswith("/product/"):
        return []

    variants: list[str] = []

    if not path.endswith("/.xaml"):
        xaml_path = path.rstrip("/") + "/.xaml"
        variants.append(urlunparse(parsed._replace(path=xaml_path)))

    characteristics_url = rewrite_read_page_url(url)
    if characteristics_url not in variants:
        variants.append(characteristics_url)

    if url not in variants:
        variants.append(url)

    return variants


# Extract product metadata from DNS-shop product HTML.
def extract_dns_metadata(raw_html: str) -> dict[str, str]:
    meta: dict[str, str] = {}

    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", raw_html, re.IGNORECASE | re.DOTALL)
    if title_match:
        meta["title"] = strip_html_fragment(title_match.group(1))[:180]

    price_match = re.search(
        r'<div[^>]+class="[^"]*product-buy__price[^"]*"[^>]*>(.*?)</div>',
        raw_html,
        re.IGNORECASE | re.DOTALL,
    )
    if price_match:
        price_text = strip_html_fragment(price_match.group(1))
        price = format_price_value(price_text)
        if price:
            meta["price"] = price
            meta["currency"] = "RUB"

    availability_patterns = (
        r"В наличии[^<]{0,120}",
        r"Под заказ[^<]{0,120}",
        r"Нет в наличии[^<]{0,120}",
        r"Р’ РЅР°Р»РёС‡РёРё[^<]{0,120}",
        r"РџРѕРґ Р·Р°РєР°Р·[^<]{0,120}",
        r"РќРµС‚ РІ РЅР°Р»РёС‡РёРё[^<]{0,120}",
    )
    for pattern in availability_patterns:
        match = re.search(pattern, raw_html, re.IGNORECASE)
        if not match:
            continue
        availability = normalize_availability(match.group(0))
        if availability:
            meta["availability"] = availability
            break

    if "availability" not in meta:
        fallback_patterns = (
            r"доступно\s*в\s*\d+\s*магазин",
            r"забрать\s*сегодня",
            r"доставка\s*завтра",
            r"РґРѕСЃС‚СѓРїРЅРѕ\s*РІ\s*\d+\s*РјР°РіР°Р·РёРЅ",
            r"Р·Р°Р±СЂР°С‚СЊ\s*СЃРµРіРѕРґРЅСЏ",
            r"РґРѕСЃС‚Р°РІРєР°\s*Р·Р°РІС‚СЂР°",
        )
        for pattern in fallback_patterns:
            match = re.search(pattern, raw_html, re.IGNORECASE)
            if not match:
                continue
            meta["availability"] = normalize_availability(match.group(0))
            if meta["availability"]:
                break

    summary_match = re.search(
        r'<meta\s+name="description"\s+content="([^"]+)"',
        raw_html,
        re.IGNORECASE,
    )
    if summary_match:
        meta["hero_summary"] = strip_html_fragment(summary_match.group(1))[:280]

    specs: list[str] = []
    for match in re.finditer(
        r'<li[^>]*class="[^"]*(?:characteristics|specs|spec)[^"]*"[^>]*>(.*?)</li>',
        raw_html,
        re.IGNORECASE | re.DOTALL,
    ):
        text = _clean_dns_spec_text(strip_html_fragment(match.group(1)))
        if text:
            specs.append(text)
        if len(specs) >= 6:
            break
    if specs:
        meta["key_specs"] = ", ".join(dict.fromkeys(specs))[:300]

    return meta
