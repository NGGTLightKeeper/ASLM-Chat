# deep-think-agent

## Overview

`deep-think-agent` is a bounded research swarm for multi-angle analysis.

Public tool:

- `deep_think(query, mode="full")`

Use it when one answer should combine several perspectives, such as:

- fact checking
- architecture
- implementation
- performance
- historical context
- UX/ethics

The tool internally selects the most relevant experts and lets them run short bounded research loops with explicit actions. `deep_think_quick` is not a public tool and should not be called directly.

---

## Tool

### `deep_think(query, mode="full")`

Arguments:

- `query`: the task or question to analyze
- `mode`: `full` or `quick`

Mode behavior:

- `full`: include the synthesized report plus raw expert sections
- `quick`: return the synthesized summary without the long raw sections

Compatibility note:

- the public MCP API stays `deep_think(query, mode="full")`
- the internal engine may use config profiles, but callers should still treat `mode` as the only public knob

---

## How The Experts Work

Experts no longer just write one long answer. They work in a short loop and can:

- reflect
- search
- use lightweight page reads when search results already include extracted content
- use Python for bounded computations
- finish once they have enough evidence

Decision payloads may also declare:

- `required_tools` when a tool must be used before finishing
- `finish_blockers` when the agent should explain why it cannot responsibly stop yet

Important architecture facts:

- each expert has isolated task state: objective, scratchpad, evidence log, tool results, confidence, and stop reason
- each expert has a hard iteration limit
- the final synthesis sees structured evidence and should downgrade unsupported claims instead of polishing them

Search-capable experts should:

- rely on retrieved evidence for exact product/model/spec claims
- use short keyword searches
- compose search queries in English by default unless the task is clearly language-specific or local
- treat lightweight search reads as real evidence, not just snippets
- keep exact names, SKUs, versions, and feature names unchanged
- split product comparisons into per-model searches when useful

Python-capable experts should:

- use the sandbox only for short bounded tasks
- avoid package installation
- treat Python as a helper for counting, parsing, transformations, and tiny simulations
- prefer Python when the user explicitly asks to count, compare numerically, convert units, or compute a formula
- declare `python` in `required_tools` when a numeric conclusion should not be produced from memory alone

They should not:

- call named products nonexistent from memory alone
- swap the user's named products for adjacent product lines without saying so
- treat weak search evidence as proof
- finish early on a computation task if Python has not been attempted yet and the environment allows it

---

## Agent Selection Heuristics

Selection is hybrid, not purely free-form.

The swarm should normally start from deterministic intent rules:

- `architect` + `implementer` for build, rewrite, migration, and system-design tasks
- add `fact_checker` for external facts, products, libraries, versions, vendors, and date-sensitive topics
- add `secops` for auth, secrets, privacy, abuse, or security topics
- add `performance` for speed, memory, throughput, and scaling questions
- add `ux_ethics` for user-facing behavior, policy, or ethical tradeoffs
- add `historian` for comparisons, precedent, and prior-art
- add `creative` only for ideation or alternatives

Optional model-based selection may add or swap one non-mandatory specialist under the active-agent cap.

Retrieval-heavy questions should prefer tool-capable experts over architecture-heavy experts.

---

## Research Escalation Rule

`deep_think` can analyze and synthesize evidence, but long-form research should still be gated.

If the task appears to need `deep_research(...)` from `mcp-web-search`, the assistant should:

```text
1. summarize the research scope
2. present a brief plan
3. ask for explicit user confirmation
4. only then start deep_research(...)
```

Do not trigger long-running research immediately just because the topic is broad.

Also do not use `deep_think` as a substitute for open-ended crawling, large dataset collection, or deep multi-page reporting.

---

## Recommended Usage Pattern

### Normal analytical question

```text
1. call deep_think(query, mode="quick" or "full")
2. inspect the synthesis
3. if more direct source work is needed, use mcp-web-search separately
```

### Broad research request

```text
1. call deep_think(...) to structure the problem or expose uncertainties
2. present a brief research plan
3. wait for explicit user confirmation
4. run deep_research(...) through mcp-web-search
```

### Good fit examples

```text
- "Compare two architectural directions and tell me which is safer to implement."
- "Check whether this product claim is real and summarize the tradeoffs."
- "Find a YouTube lecture, inspect the transcript, and count a few key terms."
- "Get the current temperature in Tokyo and convert it."
```

### Poor fit examples

```text
- "Read this exact URL and give me the text."          -> prefer read_page
- "Click through this login flow and submit the form." -> prefer browser tools
- "Run a long open-ended market research project."     -> plan first, then deep_research
```

---

## Output Expectations

Good output should:

- stay on the user's exact entities
- separate verified from unverified claims
- show tradeoffs
- avoid fake certainty
- make tool usage visible when it mattered to the answer
- reflect uncertainty when retrieval is weak or conflicting

Bad output:

- "these models do not exist" without source-backed proof
- unrelated security warnings for ordinary hardware comparisons
- broad generic advice that ignores the named products

---

## Summary

| Field | Value |
| --- | --- |
| Public tool | `deep_think` |
| Best use case | multi-perspective bounded analysis |
| Search behavior | explicit search plus lightweight retrieval inside the bounded research loop |
| Python behavior | bounded helper for counting, parsing, unit conversion, and tiny simulations |
| Agent model | hybrid selector + bounded expert loops + evidence-aware synthesis |
| Long research rule | plan first, then explicit user confirmation |
| Avoid | direct long-form research without confirmation, unsupported nonexistence claims |
