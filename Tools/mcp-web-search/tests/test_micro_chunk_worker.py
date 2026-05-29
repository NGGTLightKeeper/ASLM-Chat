from __future__ import annotations

from core.extract.micro_chunk_worker import prune_micro_chunks


def test_numeric_variants_not_broken_by_micro_split() -> None:
    query = "openssl cve critical patch rce"
    text = (
        "Noise openssl patch rce now, buy now, free now! "
        "Facts: value 2.5 and 2,5 and 2 . 5 and 2. 5 and 2 .5 and 2 , 5 and 2, 5 and 2 ,5 "
        "and ratio 2/5 and 2 / 5."
    )
    out, _ = prune_micro_chunks(text, query)
    # Keep numeric punctuation variants present after processing.
    assert "2.5" in out
    assert "2,5" in out
    assert "2 . 5" in out or "2.5" in out
    assert "2 / 5" in out or "2/5" in out


def test_surgically_drops_query_dense_fact_poor_clause() -> None:
    query = "cve openssl critical patch rce"
    text = (
        "CVE openssl critical patch rce cve openssl critical patch rce, "
        "CVE-2024-5535 CVSS 9.1 fixed in 3.0.14 at 2024-07-09."
    )
    out, dbg = prune_micro_chunks(text, query)
    assert "CVE-2024-5535" in out
    assert "CVSS 9.1" in out
    assert dbg.clauses_dropped >= 1


def test_reference_overlap_prunes_serp_like_clause() -> None:
    query = "openssl patch"
    reference = "openssl critical patch rce buy now free download"
    text = (
        "openssl critical patch rce buy now free download, "
        "CVE-2024-5535 CVSS 9.1 fixed in 3.0.14."
    )
    out, dbg = prune_micro_chunks(text, query, reference_text=reference)
    assert "CVE-2024-5535" in out
    assert dbg.clauses_dropped >= 1


def test_drops_whole_sentence_if_only_tumor_remains() -> None:
    query = "openssl critical patch rce"
    text = (
        "OpenSSL critical patch rce openssl critical patch rce, "
        "openssl critical patch rce now."
    )
    out, dbg = prune_micro_chunks(text, query)
    assert out == ""
    assert dbg.sentences_dropped >= 1
