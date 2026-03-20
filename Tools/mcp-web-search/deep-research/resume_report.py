# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.append(os.path.dirname(__file__))

from scripts.deep_research import SAFETY_PREFIX
from src.config import ResearchConfig
from src.llm_client import call_llm, close_session as close_llm_session


# Report synthesis flow.
async def main() -> None:
    """Load saved sources, build a prompt, and regenerate the final report."""

    import argparse

    parser = argparse.ArgumentParser(description="Resume report synthesis")
    parser.add_argument(
        "target_dir",
        help="Path to the investigation output directory (for example, _out/20260222...)",
    )
    args = parser.parse_args()

    cfg = ResearchConfig()
    target_dir = Path(args.target_dir)
    sources_file = target_dir / "sources.md"
    content = sources_file.read_text(encoding="utf-8")

    # Recover the original research question from the saved sources file.
    question = ""
    question_match = re.search(r"\*\*Question:\*\*\s*(.+)", content, re.IGNORECASE)
    if question_match:
        question = question_match.group(1).strip()

    # Rebuild a compact source list that the synthesis model can consume reliably.
    sources_block = ""
    blocks = content.split("## [")
    for block in blocks[1:]:
        header_line = block.split("\n", 1)[0]
        try:
            doc_id, title = header_line.split("]", 1)
            doc_id = doc_id.strip()
            title = title.strip()
        except Exception:
            continue

        url = ""
        url_match = re.search(r"-\s*\*\*URL:\*\*\s*(.+)", block)
        if url_match:
            url = url_match.group(1).strip()

        summary = ""
        summary_match = re.search(r"### Summary(.*?)(### Content)", block, re.DOTALL)
        if summary_match:
            summary = summary_match.group(1).strip()

        if url and summary:
            sources_block += f"\n[{doc_id}] {url}\nTitle: {title}\nSummary: {summary}\n"

    print(f"Parsed {len(blocks) - 1} sources. Synthesizing report. This might take a few minutes...")

    prompt = f"""{SAFETY_PREFIX}

You are an expert research analyst. Write a thorough, publication-quality research report.

Research question: "{question}"

Sources:
{sources_block}

=== REPORT STRUCTURE ===

# [Descriptive Title]

## Executive Summary
2-4 paragraphs with specific facts, numbers, and dates.

## [Core topic: definition, overview, how it works]
Deep explanation with numbered lists for key properties or steps.

## [Technical details: specs, architecture, benchmarks, comparison]
Technical deep-dive with specific numbers, versions, performance figures.
Use Markdown TABLE when comparing versions, products, or metrics.

## [Practical: use cases, availability, pricing, access]
Concrete, actionable details with inline citations.

## Contradictions and Information Gaps

## Conclusions

=== FORMATTING RULES ===

1. CITATIONS: After EVERY fact add [N].
2. TABLES: Use when comparing.
3. CODE BLOCKS: For commands, configs, API syntax.
4. BOLD key terms on first use.
5. Each section: 3-6 paragraphs. This is a DEEP report, NOT a summary.
6. LANGUAGE: Same as the research question.
7. Use ONLY facts from sources. No outside knowledge.
8. DEDUPLICATION: Never repeat the same information.

=== BEGIN REPORT ==="""

    report = await call_llm(
        prompt=prompt,
        model=cfg.synthesis_model,
        temperature=0.3,
        max_tokens=cfg.synthesis_max_tokens,
        timeout=cfg.llm_timeout,
    )

    if report:
        report_file = target_dir / "report_fixed.md"
        report_file.write_text(report, encoding="utf-8")
        print(f"Report saved to: {report_file}")
        return

    print("The report was not generated. The LLM may have timed out or returned an error.")


# Local runner entry point.
if __name__ == "__main__":

    # Async shutdown helpers.
    async def _entry() -> None:
        """Run the tool and always close the shared LLM session."""

        try:
            await main()
        finally:
            await close_llm_session()

    asyncio.run(_entry())
