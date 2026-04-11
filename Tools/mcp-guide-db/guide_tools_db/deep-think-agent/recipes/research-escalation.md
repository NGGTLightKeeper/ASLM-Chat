---
title: "Research Escalation"
domain: analysis
trigger: "A question starts analytical but needs full-scale research to answer properly"
tools: [deep_think, web_search, deep_research]
related_guides: [deep-think-agent, mcp-web-search]
difficulty: hard
---

## Goal

Handle the transition from bounded analysis to full-scale research when the question is too broad for deep_think alone.

## When to use

- deep_think returned a synthesis with too many unresolved uncertainties
- The topic has more angles than a bounded swarm can cover
- User explicitly asks for deeper investigation than what deep_think provides
- The question requires many sources and cross-checking

## When NOT to use

- deep_think already answered the question adequately
- The question is simple enough for web_search alone
- User just wants a quick perspective, not a report

## Workflow

### Step 1 -- Start with deep_think

```text
deep_think("initial question", mode="quick")
```

Use the synthesis to identify:
- What is known vs. unknown
- Which angles need more evidence
- Whether the scope requires full research

### Step 2 -- Assess escalation need

If deep_think answered sufficiently -- deliver the answer. Done.

If not -- continue to step 3.

### Step 3 -- Present a research plan

Write a brief plan:
- What topics need deeper investigation
- Expected depth (low/medium/high)
- What the output will look like

### Step 4 -- Wait for user confirmation

This is mandatory. Do not proceed without explicit approval.

### Step 5 -- Execute deep_research

```text
deep_research("detailed query covering all required angles", depth="medium")
```

### Step 6 -- Combine results

Merge deep_think's structural analysis with deep_research's source-backed evidence.
Present a unified report with:
- Structural analysis (from deep_think)
- Evidence-backed details (from deep_research)
- Explicit gaps and uncertainties

## Stop conditions

- Combined analysis provides a complete answer
- Or: user declined the research plan -- deliver deep_think results as-is with caveats

## Anti-patterns

- Skipping deep_think and going straight to deep_research
- Starting deep_research without a plan and user confirmation
- Running both deep_think and deep_research at full depth when one would suffice
- Ignoring the deep_think output and treating deep_research as the only source
- Running deep_research more than once per conversation
