---
title: "Update SEO and Shopping Parser"
date: 2026-06-22T07:46:09Z
draft: false
description: "Fixes for shopping parsers to filter false products and deduplicate facets, implementation of identity-blind SEO slug penalties, and deduplication of near-duplicates in web search."
---

## New Features

- **[Web Search]**: Implemented identity-blind SEO trim by adding a gentle penalty (`seo_slug_penalty`) for year-stuffed farm slugs based on URL shape (e.g., high hyphen density and a year), avoiding domain favouritism.
- **[Web Search]**: Added a new near-duplicate deduplication mechanism (`_dedupe_near_duplicates`) to collapse same-host variants like redirect stubs or anchor variants from search results while preserving distinct pages.
- **[Documentation]**: Added documentation for newly implemented functions `_is_listing_or_facet_url` and `_is_rating_anchor` in `parse.md`, `seo_slug_penalty` in `quality.md`, and `_dedupe_near_duplicates` in `web_search.md`.

## Bug Fixes

- **[Shopping Parser]**: Enhanced shopping product card parsing to filter out category/filter listings and rating sub-links, preventing them from masquerading as standalone products with bogus context-level prices.
- **[Shopping Parser]**: Improved the URL deduplication logic for products to strip fragments and query strings, preventing facet/tracking variants of the same item from showing as separate entries.

## API Changes

- N/A

## Known Issues

- N/A
