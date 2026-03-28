---
title: "Factual Lookup"
domain: web-research
trigger: "User asks a factual question that needs a quick web answer"
tools: [web_search, read_page]
related_guides: [mcp-web-search]
difficulty: easy
---

## Goal

Answer a factual question using the shortest web search path.

## When to use

- User asks a specific fact, name, date, spec, version, or status
- User asks "what is X" or "is X true"
- User needs a current price, release date, or availability check

## When NOT to use

- User wants a detailed comparison -- use `comparison-workflow`
- User wants a report or deep analysis -- use `deep-research-workflow`
- User asks about code or a repo -- use sandbox tools

## Workflow

### Step 1 -- Search

```text
web_search("short keyword query")
```

Use compact English keywords. Preserve exact product names and SKUs.

### Step 2 -- Check previews

Read the Preview/Snippet fields in results.
If the answer is already there -- answer immediately.

### Step 3 -- Read if needed

Only if previews are insufficient:

```text
read_page("https://best-result-url.com/article")
```

### Step 4 -- Answer

Cite the source. If evidence is ambiguous, say so instead of guessing.

## Stop conditions

- The fact is confirmed from preview or page read
- Or: no results found after 2 query refinements -- report as inconclusive

## Anti-patterns

- Long conversational queries instead of keywords
- Reading multiple pages when the preview already answers
- Declaring something nonexistent after a single weak search
- Mutating exact product names in queries
