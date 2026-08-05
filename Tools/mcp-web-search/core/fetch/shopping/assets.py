# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import re
from urllib.parse import urlencode


class ShoppingAssetCache:
    # Shopping only emits the shared UI favicon proxy URL. Fetching, validation,
    # and disk caching live in Apps.UI.views.favicon_api, like normal search.
    def favicon_proxy_url(self, domain: str) -> str:
        clean_domain = str(domain or "").strip().lower().removeprefix("www.")
        if not clean_domain or re.search(r"[^a-z0-9.-]", clean_domain):
            return ""
        return f"/api/favicon/?{urlencode({'domain': clean_domain})}"
