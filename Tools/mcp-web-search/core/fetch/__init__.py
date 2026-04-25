# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from .ddgs_client import DDGSClient, async_ddgs_search, get_ddgs_client, normalize_snippet
from .page_fetcher import PageFetcher, is_antibot, is_skippable
from .camoufox_fetcher import (
    FetchResult,
    is_camoufox_available,
    fetch_with_camoufox,
    fetch_batch_with_camoufox,
)
from .download_types import get_download_info, ALLOWED_EXTENSIONS, BLOCKED_EXTENSIONS
from .academic_fetcher import AcademicFetcher

__all__ = [
    "DDGSClient", "async_ddgs_search", "get_ddgs_client", "normalize_snippet",
    "PageFetcher", "is_antibot", "is_skippable",
    "FetchResult", "is_camoufox_available", "fetch_with_camoufox", "fetch_batch_with_camoufox",
    "get_download_info", "ALLOWED_EXTENSIONS", "BLOCKED_EXTENSIONS",
    "AcademicFetcher",
]
