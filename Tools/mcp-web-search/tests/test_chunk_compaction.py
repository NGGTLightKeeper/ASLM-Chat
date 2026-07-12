# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Single-policy chunk compaction: relevance selection + SEO-stuffing rejection."""

from __future__ import annotations

from core.extract.chunk_compaction import compress_chunks


def _doc() -> str:
    paras = []
    for i in range(40):
        if i % 4 == 0:
            paras.append(
                f"Transformer attention scales with sequence length via softmax over "
                f"query-key dot products; multi-head attention section {i}."
            )
        else:
            paras.append(f"Unrelated filler paragraph {i} about cooking and travel, low relevance.")
    return "\n\n".join(paras)


def test_compress_selects_relevant_and_compacts():
    doc = _doc()
    out = compress_chunks(doc, "transformer attention mechanism", char_budget=1_400)
    assert 0 < len(out) < len(doc)                       # compacted, not passthrough
    assert "attention" in out.lower()                    # relevant chunks survive
    assert out.lower().count("attention") >= out.lower().count("cooking")


def test_compress_respects_budget_scaling():
    doc = _doc()
    small = compress_chunks(doc, "transformer attention mechanism", char_budget=600)
    large = compress_chunks(doc, "transformer attention mechanism", char_budget=3_000)
    assert len(small) <= len(large)


def test_compress_rejects_seo_stuffed_block():
    spam = "buy attention attention attention cheap attention deals attention shop attention now " * 3
    real = (
        "The transformer uses scaled dot-product attention to weight tokens by relevance, "
        "computed as softmax of query-key products divided by the square root of the dimension."
    )
    out = compress_chunks(f"{spam}\n\n{real}", "transformer attention", char_budget=1_400)
    assert "softmax" in out                # genuine content kept
    assert "cheap attention deals" not in out  # SEO-stuffed block rejected


def test_compress_empty_query_does_not_crash():
    doc = _doc()
    out = compress_chunks(doc, "", char_budget=1_400)
    assert isinstance(out, str)


def test_compress_chunks_keeps_selected_fence_atomic():
    code = (
        "```python\n"
        "# Transformer attention query computes 42 token weights.\n"
        "async def attention_query():\n"
        "    return transformer_attention_result\n"
        "```"
    )
    filler = "Unrelated cooking and travel paragraph with enough words to be scored."
    doc = "\n\n".join([filler] * 8 + [code] + [filler] * 8)

    out = compress_chunks(doc, "transformer attention query", char_budget=600)

    assert code in out
    assert out.count("```") == 2


def test_compress_chunks_pins_irrelevant_code_verbatim_over_budget():
    code = (
        "```python\n"
        + "\n".join(f"preserved_value_{i} = {i}" for i in range(80))
        + "\n```"
    )
    relevant = (
        "Transformer attention uses query-key products to compute token relevance."
    )

    out = compress_chunks(f"{relevant}\n\n{code}", "transformer attention", char_budget=300)

    assert code in out
    assert len(out) > 300
