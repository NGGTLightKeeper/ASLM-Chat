# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import pytest

from core.fetch.shopping.assets import ShoppingAssetCache


@pytest.mark.unit
def test_asset_cache_only_exposes_favicon_proxy_url() -> None:
    cache = ShoppingAssetCache()

    assert not hasattr(cache, "ensure_favicon")
    assert not hasattr(cache, "cached_favicon_url")
    assert not hasattr(cache, "ensure_product_image")


@pytest.mark.unit
def test_favicon_proxy_url_is_stable() -> None:
    cache = ShoppingAssetCache()

    assert cache.favicon_proxy_url("www.Example.COM") == "/api/favicon/?domain=example.com"


@pytest.mark.unit
def test_favicon_proxy_url_rejects_unsafe_domain_text() -> None:
    cache = ShoppingAssetCache()

    assert cache.favicon_proxy_url("example.com/path") == ""
    assert cache.favicon_proxy_url("localhost:8000") == ""
