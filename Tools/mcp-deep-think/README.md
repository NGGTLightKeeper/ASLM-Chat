# mcp-deep-think

Tool-driven multi-agent research swarm for bounded deep analysis.

## What Changed

Deep Think no longer relies on agents mostly free-writing long text blocks.
It now runs a shared execution engine where each selected specialist can iterate through:

- `reflect`
- `search`
- `python`
- `finish`

Each run writes artifacts into `_out/<task_id>/` and can be launched either through MCP or as a standalone CLI script.

## Public MCP Tool

### `deep_think(query, mode="full")`

- `query`: question or task to analyze
- `mode`: `full` or `quick`

The public signature stays compatible with the previous version.

## Standalone CLI

```bash
python scripts/deep_think.py "Rewrite deep think as a research swarm" --profile balanced --mode full
```

Arguments:

- `query`
- `--mode {full,quick}`
- `--profile {quick,balanced,research}`
- `--id <task_id>`

## Configuration

Primary config lives in:

`config/deep_think_config.json`

Main sections:

- `llm`
- `search`
- `sandbox`
- `limits`
- `profiles`
- `agents`
- `output`

Legacy `DEEP_THINK_*` environment variables are still accepted as overrides for compatibility.

## Architecture

1. Hybrid selector chooses the swarm.
2. Agents run bounded research loops in parallel.
3. Agents can use shared search and Python sandbox adapters.
4. Arbiter synthesizes the final report from structured evidence and tool logs.
5. Artifacts are written to `_out/<task_id>/`.

## Output Artifacts

Each run can write:

- `report.md`
- `report.json`
- `trace.json`
- `events.jsonl`

## Notes

- Search is the default grounding tool for factual work.
- Python execution is limited to short bounded computations.
- Page reading/crawling is intentionally out of scope for this rewrite.
