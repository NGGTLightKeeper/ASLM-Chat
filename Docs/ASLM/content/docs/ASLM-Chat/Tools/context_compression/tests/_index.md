---
title: "tests"
draft: false
---

## Package `tests`

`Tools/context_compression/tests/` — Pytest suite for compression decision, summary fitting, parser fallbacks, sanitization, and fat-chat fixtures.

`conftest.py` adds `Tools/` to `sys.path` for imports.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [cache_chat_utils](cache_chat_utils/) | `cache_chat_utils.py` | SQLite helpers for offline fat-chat experiments |
| [build_fat_chat_summary](build_fat_chat_summary/) | `build_fat_chat_summary.py` | Dev CLI: raw summary from largest cached chat |
| [run_live_fat_compression](run_live_fat_compression/) | `run_live_fat_compression.py` | Dev CLI: raw vs live LLM summary + sanitization report |
| [conftest](conftest/) | `conftest.py` | `sys.path` setup |
| [test_compression_decision](test_compression_decision/) | `test_compression_decision.py` | `decide_compression`, context window |
| [test_fit_summary_text](test_fit_summary_text/) | `test_fit_summary_text.py` | Budget fitting |
| [test_build_summary_fallback](test_build_summary_fallback/) | `test_build_summary_fallback.py` | Unparseable model output fallback |
| [test_summary_parser_cases](test_summary_parser_cases/) | `test_summary_parser_cases.py` | Parser fixture cases |
| [test_history_compressor_sanitize](test_history_compressor_sanitize/) | `test_history_compressor_sanitize.py` | Sanitization rules |
| [test_fat_chat_summary](test_fat_chat_summary/) | `test_fat_chat_summary.py` | Fat-chat fixture bounds |

---

## Related

- [context_compression](../_index/)
- [history_compressor](../history_compressor/)
