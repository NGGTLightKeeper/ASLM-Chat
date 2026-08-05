# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Comment

from .models import ShoppingProduct


PRICE_MARKER_RE = r"[$€£₽₴¥]|zł(?!\w)|руб\.?(?!\w)|грн\.?(?!\w)|р\.?(?!\w)|円"
PRICE_CURRENCY_FIRST_RE = re.compile(
    rf"(?P<currency>{PRICE_MARKER_RE})\s*"
    r"(?P<amount>\d[\d\s.,]{1,14})",
    re.IGNORECASE,
)
PRICE_AMOUNT_FIRST_RE = re.compile(
    r"(?P<amount2>\d[\d\s.,]{1,14})\s*"
    rf"(?P<currency2>{PRICE_MARKER_RE})",
    re.IGNORECASE,
)
CURRENCY_MAP = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "₽": "RUB", "руб": "RUB", "руб.": "RUB", "р": "RUB", "р.": "RUB",
    "₴": "UAH", "грн": "UAH", "грн.": "UAH",
    "¥": "JPY", "円": "JPY",
    "zł": "PLN",
}


def compact(text: str, *, limit: int = 260) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()[:limit].rstrip()


def source_domain(url: str) -> str:
    return (urlparse(url or "").netloc or "").lower().removeprefix("www.")


def normalize_url(raw: str, base: str = "") -> str:
    value = html.unescape(raw or "").strip()
    if not value:
        return ""
    if value.startswith("/url?") or value.startswith("https://www.google.") and "/url?" in value:
        target = parse_qs(urlparse(value).query).get("q", [""])[0]
        if target:
            value = target
    if value.startswith("//"):
        value = "https:" + value
    if base and value.startswith("/"):
        value = urljoin(base, value)
    return value


def parse_price(text: str, *, default_currency: str = "", allow_bare: bool = False) -> tuple[str, float | None, str]:
    source = text or ""
    match = None
    for candidate in PRICE_CURRENCY_FIRST_RE.finditer(source):
        if candidate.start() > 0 and source[candidate.start() - 1] in "0123456789,.":
            continue
        match = candidate
        break
    if match is None:
        for candidate in PRICE_AMOUNT_FIRST_RE.finditer(source):
            if candidate.end() < len(source) and source[candidate.end() : candidate.end() + 1].isdigit():
                continue
            if _bare_integer_before_spaced_currency(candidate.group("amount2") or ""):
                continue
            match = candidate
            break
    if not match:
        if not allow_bare:
            return "", None, ""
        bare_amount = parse_amount_value(source)
        if bare_amount is None:
            return "", None, ""
        return compact(source, limit=80), bare_amount, default_currency.upper()
    groups = match.groupdict()
    currency_raw = (groups.get("currency") or groups.get("currency2") or "").lower().rstrip(".")
    amount_raw = groups.get("amount") or groups.get("amount2") or ""
    amount = parse_amount_value(amount_raw)
    if amount is None:
        return "", None, ""
    if _looks_like_rating_ruble_false_positive(match, source, amount):
        return "", None, ""
    currency = CURRENCY_MAP.get(currency_raw, currency_raw.upper()) or default_currency.upper()
    return compact(match.group(0), limit=80), amount, currency


def parse_amount_value(raw: str) -> float | None:
    value = (raw or "").replace("\xa0", " ").strip()
    if not value or re.search(r"[^\d\s.,]", value):
        return None
    value = re.sub(r"\s*([,.])\s*", r"\1", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value or not re.search(r"\d", value):
        return None

    decimal_sep = ""
    if "," in value and "." in value:
        decimal_sep = "," if value.rfind(",") > value.rfind(".") else "."
    elif value.count(",") == 1:
        tail = value.rsplit(",", 1)[1]
        decimal_sep = "," if 1 <= len(tail) <= 2 else ""
    elif value.count(".") == 1:
        tail = value.rsplit(".", 1)[1]
        decimal_sep = "." if 1 <= len(tail) <= 2 else ""

    if decimal_sep:
        integer_part, decimal_part = value.rsplit(decimal_sep, 1)
        if not decimal_part.isdigit() or len(decimal_part) > 2:
            return None
    else:
        integer_part, decimal_part = value, ""

    other_sep = "." if decimal_sep == "," else ","
    grouping_sep = ""
    if decimal_sep:
        grouping_sep = other_sep if other_sep in integer_part else ""
    elif "," in integer_part and "." not in integer_part:
        grouping_sep = ","
    elif "." in integer_part and "," not in integer_part:
        grouping_sep = "."

    if grouping_sep:
        groups = integer_part.split(grouping_sep)
        if not _valid_grouped_integer(groups):
            return None
        integer_digits = "".join(groups)
    elif other_sep in integer_part:
        groups = integer_part.split(other_sep)
        if not _valid_grouped_integer(groups):
            return None
        integer_digits = "".join(groups)
    elif " " in integer_part:
        groups = integer_part.split(" ")
        if not _valid_grouped_integer(groups):
            return None
        integer_digits = "".join(groups)
    else:
        integer_digits = integer_part

    if not integer_digits.isdigit():
        return None

    normalized = integer_digits
    if decimal_part:
        normalized = f"{normalized}.{decimal_part}"
    try:
        return float(normalized)
    except ValueError:
        return None


def _bare_integer_before_spaced_currency(raw: str) -> bool:
    value = raw or ""
    stripped = value.strip()
    # Four bare digits are commonly a model number (`RTX 5070 £...`). Five or
    # more digits are also a normal ungrouped marketplace price (`51673 ₽`).
    return len(stripped) == 4 and stripped.isdigit() and value[-1:].isspace()


def _looks_like_rating_ruble_false_positive(match: re.Match[str], source: str, amount: float) -> bool:
    groups = match.groupdict()
    currency_raw = (groups.get("currency") or groups.get("currency2") or "").lower().rstrip(".")
    if currency_raw != "р" or amount > 5:
        return False
    before = source[max(0, match.start() - 18):match.start()].lower()
    after = source[match.end():match.end() + 18].lower()
    return "рейтинг" in before or "рейтинг" in after or "rating" in before or "rating" in after


def _valid_grouped_integer(groups: list[str]) -> bool:
    if len(groups) <= 1:
        return bool(groups and groups[0].isdigit())
    if not groups[0].isdigit() or not (1 <= len(groups[0]) <= 3):
        return False
    return all(group.isdigit() and len(group) == 3 for group in groups[1:])


def product_id(url: str, title: str, source: str) -> str:
    payload = f"{source}\n{url}\n{title}".encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()[:16]


def score_product(product: ShoppingProduct) -> float:
    score = 0.2
    if product.price_text:
        score += 0.35
    if product.url.startswith("http"):
        score += 0.15
    if product.snippet:
        score += 0.1
    if product.seller or product.availability:
        score += 0.1
    return round(min(score, 1.0), 3)


def parse_products(
    html_text: str,
    *,
    provider: str,
    lane: str,
    method: str,
    base_url: str,
    default_currency: str = "",
) -> list[ShoppingProduct]:
    if not html_text:
        return []
    soup = BeautifulSoup(html_text, "html.parser")
    products: list[ShoppingProduct] = []
    products.extend(_jsonld_products(
        soup,
        provider=provider,
        lane=lane,
        method=method,
        base_url=base_url,
        default_currency=default_currency,
    ))
    products.extend(_card_products(
        soup,
        provider=provider,
        lane=lane,
        method=method,
        base_url=base_url,
        default_currency=default_currency,
    ))
    return _dedupe(products)


def _make_product(
    *,
    title: str,
    url: str,
    provider: str,
    lane: str,
    method: str,
    price_text: str = "",
    price_value: float | None = None,
    currency: str = "",
    snippet: str = "",
    seller: str = "",
    availability: str = "",
) -> ShoppingProduct:
    if not price_text or price_value is None or not currency:
        raise ValueError("shopping product requires a parsed price")
    product = ShoppingProduct(
        id=product_id(url, title, provider),
        title=compact(title, limit=220),
        url=url,
        source=provider,
        source_domain=source_domain(url),
        lane=lane,
        price_text=price_text,
        price_value=price_value,
        currency=currency,
        seller=seller,
        availability=availability,
        snippet=compact(snippet, limit=700),
        fetched_at=time.time(),
        meta={"method": method},
    )
    product.confidence = score_product(product)
    return product


def _jsonld_products(
    soup: BeautifulSoup,
    *,
    provider: str,
    lane: str,
    method: str,
    base_url: str,
    default_currency: str,
) -> list[ShoppingProduct]:
    out: list[ShoppingProduct] = []
    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        payload = script.get_text(" ", strip=True)
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except Exception:
            continue
        queue = data if isinstance(data, list) else [data]
        for item in queue:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                queue.extend(x for x in graph if isinstance(x, dict))
                continue
            item_type = item.get("@type")
            item_types = item_type if isinstance(item_type, list) else [item_type]
            if "Product" not in item_types:
                continue
            offers = _first_offer(item.get("offers"))
            title = compact(str(item.get("name") or ""))
            url = normalize_url(str(item.get("url") or offers.get("url") or base_url), base_url)
            price = str(offers.get("price") or "")
            currency = str(offers.get("priceCurrency") or default_currency).upper()
            price_value = parse_amount_value(price)
            price_text = compact(price, limit=80) if price_value is not None else ""
            if title and url and price_text and price_value is not None and currency:
                out.append(_make_product(
                    title=title,
                    url=url,
                    provider=provider,
                    lane=lane,
                    method=method,
                    price_text=price_text,
                    price_value=price_value,
                    currency=currency,
                    snippet=str(item.get("description") or ""),
                    availability=str(offers.get("availability") or "").rsplit("/", 1)[-1],
                ))
    return out


def _first_offer(raw: object) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                return item
    return {}


def _card_products(
    soup: BeautifulSoup,
    *,
    provider: str,
    lane: str,
    method: str,
    base_url: str,
    default_currency: str,
) -> list[ShoppingProduct]:
    out: list[ShoppingProduct] = []
    for anchor in soup.find_all("a", href=True):
        title = compact(anchor.get_text(" ", strip=True), limit=220)
        url = normalize_url(anchor.get("href", ""), base_url)
        if len(title) < 8 or not url.startswith("http"):
            continue
        # Drop category/filter listings and rating sub-links — they masquerade as products
        # but only re-list one facet/score at the page-context price (the duplicate source).
        if _is_listing_or_facet_url(url) or _is_rating_anchor(title, url):
            continue
        price_text, price_value, currency = parse_price(title, default_currency=default_currency)
        price_from_title = bool(price_text)
        context = _visible_ancestor_text(anchor, depth=3)
        if not price_text:
            context, price_text, price_value, currency = _nearest_priced_context(
                anchor, default_currency=default_currency
            )
        if _looks_like_price_filter_title(title):
            continue
        if not price_from_title and not _has_enough_product_title_signal(title):
            continue
        if not price_text or price_value is None or not currency:
            continue
        out.append(_make_product(
            title=title,
            url=url,
            provider=provider,
            lane=lane,
            method=method,
            price_text=price_text,
            price_value=price_value,
            currency=currency,
            snippet=context,
        ))
    return out


_NON_VISIBLE_TEXT_PARENTS = frozenset({"script", "style", "noscript", "noframes", "template"})


def _visible_text(node: object, *, limit: int = 1200) -> str:
    find_all = getattr(node, "find_all", None)
    if not callable(find_all):
        return ""
    strings: list[str] = []
    for item in find_all(string=True):
        if isinstance(item, Comment):
            continue
        if any(
            str(getattr(parent, "name", "") or "").lower() in _NON_VISIBLE_TEXT_PARENTS
            for parent in getattr(item, "parents", ())
            if parent is not node
        ):
            continue
        strings.append(str(item))
    return compact(" ".join(strings), limit=limit)


def _visible_ancestor_text(anchor: object, *, depth: int) -> str:
    node = anchor
    for _ in range(max(0, depth)):
        parent = getattr(node, "parent", None)
        if parent is None:
            break
        node = parent
    return _visible_text(node)


def _nearest_priced_context(
    anchor: object, *, default_currency: str
) -> tuple[str, str, float | None, str]:
    node = anchor
    last_context = ""
    # Yandex Market keeps specifications and the price in adjacent branches of
    # the product card. Four ancestors reach the common card without reaching
    # the surrounding result list; other providers usually resolve earlier.
    for _ in range(5):
        parent = getattr(node, "parent", None)
        if parent is None:
            break
        node = parent
        context = _visible_text(node)
        if context:
            last_context = context
        price_text, price_value, currency = parse_price(
            context, default_currency=default_currency
        )
        if price_text and price_value is not None and currency:
            return context, price_text, price_value, currency
    return last_context, "", None, ""


# Listing/search/facet endpoints are not products: comparison sites expose category and
# filter links (…/results?q=…&af_CATEGORY=…) that share one page-context price, so each
# facet becomes a near-duplicate "product" at the same bogus price. Product pages live on
# detail paths (…/pl/…, …/product/…) instead. Identity-blind: keys off path/query shape.
_LISTING_PATH_SEGMENTS = frozenset({
    "results", "search", "browse", "catalog", "category", "categories",
    "suche", "filter", "filters",
})


def _is_listing_or_facet_url(url: str) -> bool:
    parsed = urlparse(url or "")
    segments = {seg.lower() for seg in (parsed.path or "").split("/") if seg}
    if segments & _LISTING_PATH_SEGMENTS:
        return True
    query = (parsed.query or "").lower()
    # Facet params (af_category=, category=, filter=) mark a filtered listing, not an item.
    return bool(re.search(r"(^|&)(af_[a-z]+|category|categories|filter|facet)=", query))


# Rating/review sub-links of a product card (…#ratings, "Bewertung: 4.6 von 5 Sternen …")
# parse into a separate row at the card's price — a duplicate of the real product. Match
# only rating-dominated titles so normal titles carrying an inline score ("… 4.5 Wireless")
# are untouched.
_RATING_FRAGMENTS = frozenset({"ratings", "reviews", "rating", "review"})
_RATING_TITLE_RE = re.compile(
    r"^\s*(bewertung\b|\d+([.,]\d+)?\s*(von\s*5\s*sternen|out\s*of\s*5\s*stars?|stars?\b))",
    re.IGNORECASE,
)


def _is_rating_anchor(title: str, url: str) -> bool:
    if urlparse(url or "").fragment.lower() in _RATING_FRAGMENTS:
        return True
    return bool(_RATING_TITLE_RE.match(title or ""))


def _looks_like_price_filter_title(title: str) -> bool:
    value = compact(title, limit=120).lower()
    if not value:
        return False
    if re.match(r"^(under|unter|over|über|ueber|до|от)\s+[\d\s.,]+", value, flags=re.I):
        return True
    if re.match(r"^[\d\s.,]+\s*(?:[$€£₽₴¥]|руб\.?|грн\.?|р\.?|円)\s*[-–]\s*[\d\s.,]+", value, flags=re.I):
        return True
    if re.match(r"^[\d\s.,]+\s*[-–]\s*[\d\s.,]+\s*(?:[$€£₽₴¥]|руб\.?|грн\.?|р\.?|円)", value, flags=re.I):
        return True
    return False


def _has_enough_product_title_signal(title: str) -> bool:
    value = compact(title, limit=120).lower()
    tokens = re.findall(r"[\w]+", value, flags=re.UNICODE)
    if len(tokens) >= 4:
        return True
    return bool(re.search(r"\b[a-zа-яё]{2,}\s*\d{2,}\b|\b\d{2,}\s*[a-zа-яё]{2,}\b", value, flags=re.I))


def _dedupe(products: list[ShoppingProduct]) -> list[ShoppingProduct]:
    out: list[ShoppingProduct] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for product in sorted(products, key=lambda item: item.confidence, reverse=True):
        title_key = re.sub(r"\W+", " ", product.title.lower()).strip()[:90]
        # Strip fragment AND query so facet/tracking variants of one page
        # (…/item?hloc=eu&nocookie=1#ratings) collapse to a single product.
        url_key = product.url.split("#", 1)[0].split("?", 1)[0]
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        out.append(product)
    return out
