# deep-think-agent

## What it is

`deep-think-agent` is a bounded research swarm for multi-angle analysis.
Multiple experts work in short loops with search, reflection, and Python computation.
Returns a synthesized report combining multiple perspectives.

---

## Tools

### `deep_think(query, mode="full")`

- `query` -- the task or question to analyze
- `mode` -- `full` (synthesis + raw expert sections) or `quick` (synthesis only)

---

## How experts work

Each expert has isolated state and runs in a bounded loop:
- Reflect on the problem
- Search for evidence (keyword queries, lightweight page reads)
- Use Python for bounded computations (counting, parsing, unit conversion)
- Finish when enough evidence is gathered

Experts are selected based on task type:
- `architect` + `implementer` -- for build/design/migration tasks
- `fact_checker` -- for products, versions, vendors, date-sensitive topics
- `secops` -- for auth, secrets, privacy, security
- `performance` -- for speed, memory, throughput, scaling
- `ux_ethics` -- for user-facing behavior, policy, ethics
- `historian` -- for comparisons, precedent, prior art
- `creative` -- for ideation and alternatives

---

## Golden rules

1. Do not use for simple factual questions -- use `web_search` instead.
2. Do not use as a substitute for open-ended crawling or dataset collection.
3. If research escalation is needed, present a plan and wait for user confirmation before `deep_research`.
4. Experts should rely on retrieved evidence, not memory, for specific claims.
5. Exact names, SKUs, versions must be preserved unchanged.
6. The synthesis should downgrade unsupported claims, not polish them.

---

## Good fit

- Multi-perspective analysis ("compare these two architectures")
- Fact-checking with evidence ("is this product claim real")
- Tasks needing several expert viewpoints combined

## Poor fit

- Single URL read -- use `read_page`
- Interactive browser flow -- use browser tools
- Long open-ended market research -- use `deep_research` with plan + confirmation
