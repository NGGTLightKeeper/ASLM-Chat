---
title: "Comparison Workflow"
domain: web-research
trigger: "User asks to compare two or more products, technologies, or options"
tools: [web_search, read_page]
related_guides: [mcp-web-search]
difficulty: medium
---

## Goal

Compare multiple entities with source-backed evidence and explicit tradeoffs.

## When to use

- User asks "which is better, A or B"
- User asks to compare specs, features, prices, or reviews
- User provides 2+ products/technologies to evaluate

## When NOT to use

- User asks a single fact about one entity -- use `factual-lookup`
- User wants a deep report with many sources -- use `deep-research-workflow`

## Workflow

### Step 1 -- Parallel batch search

```text
web_search(["Product A specs review", "Product B specs review"], limit=5)
```

One query per entity. This returns grouped results.

### Step 2 -- Compare previews

Read snippets from each query group.
Identify the key differentiators from previews alone.

### Step 3 -- Deep read for the strongest sources

```text
read_page(["https://review-site.com/product-a", "https://review-site.com/product-b"])
```

Batch reads -- do not read one-by-one.
Only read pages that add information beyond what previews provided.

### Step 4 -- Structured answer

Present:
- Key specs/features side by side
- Explicit tradeoffs (where A wins, where B wins)
- Source citations for each claim
- Recommendation with reasoning (if asked)

## Stop conditions

- All entities have at least one strong source each
- Key differentiators are identified with evidence
- Tradeoffs can be stated explicitly

## Anti-patterns

- Searching for all entities in a single query (loses specificity)
- Reading 5+ pages per entity when 1-2 good sources suffice
- Making claims without source backing
- Declaring a product nonexistent after weak search results
- Swapping the user's named products for adjacent product lines without disclosure
