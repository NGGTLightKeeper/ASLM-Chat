---
title: "Deep Research Workflow"
domain: web-research
trigger: "User needs a comprehensive multi-source report or deep analysis"
tools: [web_search, read_page, deep_research]
related_guides: [mcp-web-search, deep-think-agent]
difficulty: hard
---

## Goal

Produce a thorough, source-backed research report using the deep_research pipeline.

## When to use

- User explicitly asks for deep research or a comprehensive report
- Lightweight search is insufficient -- too many angles to cover
- User needs cross-checking across multiple sources

## When NOT to use

- User asks a single fact -- use `factual-lookup`
- User asks a simple comparison -- use `comparison-workflow`
- User wants code analysis -- use sandbox tools

## Workflow

### Step 1 -- Scope the research

Identify:
- What exactly needs to be researched
- How many entities/angles are involved
- What depth is appropriate (low/medium/high/extra)

### Step 2 -- Present a plan

Write a brief research plan for the user:
- Topics to cover
- Expected depth
- Estimated scope

### Step 3 -- Wait for confirmation

Do not proceed without explicit user approval.
This is a hard rule -- deep_research is expensive in time.

### Step 4 -- Execute

```text
deep_research("detailed research query covering all angles", depth="medium")
```

### Step 5 -- Fill gaps

If the report has small gaps:

```text
web_search("specific gap query")
read_page("https://specific-source.com")
```

Do not run a second deep_research. Fill gaps with targeted search.

### Step 6 -- Present results

Structured report with:
- Key findings
- Source citations
- Explicit uncertainties
- Recommendations (if asked)

## Stop conditions

- Deep research complete and gaps filled
- Or: user declined the research plan -- fall back to lighter methods

## Anti-patterns

- Starting deep_research immediately without a plan
- Running deep_research more than once per conversation
- Using deep_research for a question that web_search can answer
- Presenting unsourced claims from the pipeline as verified facts
