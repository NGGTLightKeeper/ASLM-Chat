# Context Compression

This subproject provides structured chat-history compression for long sessions.

## Goals

- Keep critical context when history reaches budget limits.
- Preserve system instructions and latest turns untouched.
- Replace only overflowed older history with a structured summary base.
- Support debug forcing for small-context behavior (`4k`).

## Entry points

- `history_compressor.py`
  - `resolve_context_window_tokens(...)`
  - `decide_compression(...)`
  - `build_structured_history_summary(...)`

## Debug mode

Set environment variable:

- `ASLM_DEBUG_CONTEXT_COMPRESSION_4K=1`

When enabled, compression logic behaves as if the active context window were 4096 tokens.
