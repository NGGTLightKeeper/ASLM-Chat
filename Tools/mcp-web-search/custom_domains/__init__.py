"""Custom domain-specific fetch/extract routes.

These modules are intentionally kept outside the main `read_page` service so we
can iterate on domain-specific strategies without coupling them to the generic
pipeline too early.
"""

from .amazon import fetch_amazon_snapshot
from .dns_shop import dns_variant_urls, rewrite_read_page_url
from .ebay import fetch_ebay_snapshot
from .github import fetch_github_page, is_github_url
from .reddit import fetch_reddit_json, is_reddit
from .retail import extract_retail_metadata, normalize_availability, prepend_retail_metadata
from .stackexchange import fetch_stackexchange_question, is_stackexchange_question_url
from .x import fetch_x_post, is_x_post

__all__ = [
    "fetch_amazon_snapshot",
    "dns_variant_urls",
    "extract_retail_metadata",
    "fetch_ebay_snapshot",
    "fetch_github_page",
    "fetch_reddit_json",
    "fetch_stackexchange_question",
    "fetch_x_post",
    "is_reddit",
    "is_github_url",
    "is_stackexchange_question_url",
    "is_x_post",
    "normalize_availability",
    "prepend_retail_metadata",
    "rewrite_read_page_url",
]
