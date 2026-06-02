---
title: "extract"
draft: false
---

## Package `extract`

`Tools/mcp-web-search/core/extract/` — HTML/PDF → clean text, SERP previews, and read-page compression.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [content_processor](content_processor/) | `content_processor.py` | Preview pipeline, BM25/GLiNER compression |
| [page_normalizer](page_normalizer/) | `page_normalizer.py` | Trafilatura page → markdown |
| [dom_block_extractor](dom_block_extractor/) | `dom_block_extractor.py` | DOM block scoring |
| [gliner_wrapper](gliner_wrapper/) | `gliner_wrapper.py` | GLiNER entity-density path |
| [profile_chunk_selector](profile_chunk_selector/) | `profile_chunk_selector.py` | Query-type chunk budgets |
| [micro_chunk_worker](micro_chunk_worker/) | `micro_chunk_worker.py` | Sentence-level pruning |
| [nextjs_rsc](nextjs_rsc/) | `nextjs_rsc.py` | Next.js RSC payload text |
| [pdf_extractor](pdf_extractor/) | `pdf_extractor.py` | PDF → markdown |
| [scoring](scoring/) | `scoring.py` | Lexical SERP scoring |
| [chunk_quality](chunk_quality/) | `chunk_quality.py` | SEO-stuffing penalties |
| [fact_signals](fact_signals/) | `fact_signals.py` | Numeric/currency fact detectors |

---

## Related

- [core](../_index/)
- [services/read_page](../../services/read_page/)
