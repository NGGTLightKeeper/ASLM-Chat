from __future__ import annotations

from urllib.parse import urlparse

from custom_domains.citilink import extract_citilink_metadata
from custom_domains.dns_shop import extract_dns_metadata
from custom_domains.retail_common import normalize_availability, prepend_retail_metadata


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")


def extract_retail_metadata(url: str, raw_html: str) -> dict[str, str]:
    host = _host(url)
    if host == "citilink.ru":
        return extract_citilink_metadata(raw_html)
    if host == "dns-shop.ru":
        return extract_dns_metadata(raw_html)
    return {}
