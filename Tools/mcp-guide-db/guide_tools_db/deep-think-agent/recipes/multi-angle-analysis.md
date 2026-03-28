---
title: "Multi-Angle Analysis"
domain: analysis
trigger: "User asks a question that benefits from multiple expert perspectives"
tools: [deep_think]
related_guides: [deep-think-agent]
difficulty: medium
---

## Goal

Produce a structured analysis combining multiple expert viewpoints on a question.

## When to use

- User asks to evaluate an architecture, design, or strategy
- User asks to fact-check a claim with evidence
- User asks a question with multiple dimensions (technical, security, UX, performance)
- User asks "what are the tradeoffs of X"

## When NOT to use

- User asks a simple factual question -- use `web_search`
- User asks to read a specific URL -- use `read_page`
- User asks for long-form open-ended research -- use `deep-research-workflow`

## Workflow

### Step 1 -- Assess the question

Determine:
- Is this genuinely multi-angle? (2+ perspectives needed)
- What mode is appropriate? (`quick` for short synthesis, `full` for detailed)

### Step 2 -- Call deep_think

```text
deep_think("user's question with full context", mode="full")
```

Include all relevant context in the query -- product names, constraints, goals.

### Step 3 -- Review the synthesis

Check:
- Are claims backed by evidence?
- Are uncertainties explicitly stated?
- Does the answer stay on the user's exact entities?

### Step 4 -- Fill gaps if needed

If the synthesis has specific gaps:

```text
web_search("specific gap query")
read_page("https://specific-source.com")
```

Do not run `deep_think` again for gap-filling.

### Step 5 -- Present to user

Present the synthesis with:
- Key findings per perspective
- Explicit tradeoffs
- Source-backed claims vs. uncertain claims
- Recommendation (if asked)

## Stop conditions

- Synthesis answers the user's question from multiple angles
- Or: the question is too narrow for deep_think -- answer directly instead

## Anti-patterns

- Using deep_think for a question that web_search can answer in one step
- Running deep_think multiple times for the same question
- Ignoring unsupported claims in the synthesis
- Not including enough context in the query (vague questions get vague answers)
- Using deep_think as a replacement for deep_research on broad topics
