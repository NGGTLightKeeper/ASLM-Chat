# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Prompts and JSON schemas for agentic deep research."""

from __future__ import annotations

from typing import Any

from services.deep_research.models import ResearchSession
from services.deep_research.session import build_reflection_summary


def decision_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["thought", "confidence", "action", "action_input"],
        "properties": {
            "thought": {"type": "string", "minLength": 1, "maxLength": 600},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "action": {
                "type": "string",
                "enum": ["reflect", "web_search", "academic_search", "read_page", "site_map", "python", "import_web_file", "finish"],
            },
            "action_input": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string"},
                    "domains": {"type": "array", "items": {"type": "string"}},
                    "url": {"type": "string"},
                    "filename": {"type": "string"},
                    "topic": {"type": "string"},
                    "source": {"type": "string"},
                    "mode": {"type": "string"},
                    "code": {"type": "string"},
                    "claims": {"type": "array", "items": {"type": "string"}},
                    "gaps": {"type": "array", "items": {"type": "string"}},
                    "used_source_ids": {"type": "array", "items": {"type": "string"}},
                    "recommended_followups": {"type": "array", "items": {"type": "string"}},
                    "summary": {"type": "string"},
                    "synthesis_ready": {"type": "boolean"},
                    "request_extra_quota": {"type": "boolean"},
                },
            },
        },
    }


def synthesis_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "summary", "sections", "sources"],
        "properties": {
            "title": {"type": "string", "minLength": 1},
            "summary": {"type": "string", "minLength": 1},
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["heading", "body"],
                    "properties": {
                        "heading": {"type": "string"},
                        "body": {"type": "string"},
                    },
                },
            },
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "title", "url"],
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                    },
                },
            },
        },
    }


def _quota_notice(session: ResearchSession) -> str:
    """Return an extra-quota notice when any budget is exhausted and quota unused."""
    if session.extra_quota_used:
        return ""
    cfg = session.config
    exhausted = []
    if session.search_calls >= int(cfg.max_search_calls) + session.extra_search_quota:
        exhausted.append(f"web_search (+{int(getattr(cfg, 'extra_quota_search_calls', 7))} available)")
    if session.read_calls >= int(cfg.max_read_calls) + session.extra_read_quota:
        exhausted.append(f"read_page (+{int(getattr(cfg, 'extra_quota_read_calls', 7))} available)")
    if not exhausted:
        return ""
    tools_str = " and ".join(exhausted)
    return (
        f"\n[BUDGET EXHAUSTED: {tools_str}]\n"
        "You may request a one-time quota extension by choosing action `reflect` with "
        "`request_extra_quota: true` in action_input. "
        "Only do this if the research is genuinely incomplete and more tool calls would "
        "materially improve the report quality.\n"
    )


def _overdrive_action_doc(session: ResearchSession) -> str:
    """Return import_web_file action line when sandbox is available."""
    sandbox = getattr(session, "sandbox", None)
    if sandbox is None or not getattr(sandbox, "running", False):
        return ""
    settings = getattr(session, "overdrive_settings", None)
    max_mb = getattr(settings, "import_file_max_size_mb", 100) if settings else 100
    return (
        f"- import_web_file: download a file from the web into the sandbox workspace (max {max_mb} MB).\n"
        "  Use when you need to analyze a PDF, dataset, or archive that cannot be read via read_page.\n"
        "  After download, use `python` to read/parse the file at the returned path.\n"
        '  action_input: {"url": "https://...", "filename": "optional_name.pdf"}'
    )


def build_controller_prompt(session: ResearchSession, step: int) -> str:
    cfg = session.config
    overdrive_mode = getattr(session, "sandbox", None) is not None
    remaining = {
        "search": int(cfg.max_search_calls) + session.extra_search_quota - session.search_calls,
        "read_page": int(cfg.max_read_calls) + session.extra_read_quota - session.read_calls,
        "python": int(cfg.max_python_calls) - session.python_calls,
    }
    ctx_used = session.context_size_estimate()
    ctx_budget = cfg.effective_tool_context_budget
    ctx_pct = int(100 * ctx_used / max(1, ctx_budget))
    minimums = {
        "search_before_finish": int(getattr(cfg, "min_search_calls_before_finish", 0)),
        "read_before_finish": int(getattr(cfg, "min_read_calls_before_finish", 0)),
    }
    quota_notice = _quota_notice(session)
    overdrive_action = _overdrive_action_doc(session)
    mode_line = "Mode: OVERDRIVE (ephemeral sandbox active)" if overdrive_mode else ""
    return f"""You are an autonomous research controller.

Question:
{session.question}

Step: {step}/{cfg.max_steps}
Elapsed: {session.elapsed:.1f}s of {cfg.total_timeout_sec:.0f}s
Content type: {cfg.content_type}
{mode_line}
Context used: {ctx_used:,} / {ctx_budget:,} chars ({ctx_pct}%)
Remaining tool calls: {remaining}
Minimum evidence before finish: {minimums}
{quota_notice}
Available actions:
- reflect: update working claims/gaps without using a tool.
- web_search: search the open web. action_input: {{"query": "compact English search query"}}
- academic_search: search peer-reviewed aggregators (arXiv, OpenAlex, PubMed, Crossref, CORE, DOAJ).
  Use for scientific papers, citations, preprints. Much better than web_search for research questions.
  action_input: {{"query": "search terms", "domains": ["arxiv.org", "openalex.org"]}}  (domains optional)
- read_page: read a known source. action_input: {{"source": "S001 or URL", "mode": "full|chunks|window|find|summary_stub", "query": "optional terms"}}
- site_map: BFS-crawl a specific domain to discover thematically relevant subpages.
  Use when a known domain (e.g. arxiv paper, docs site) likely has more relevant pages not yet indexed.
  action_input: {{"url": "https://...", "topic": "focus topic for pruning"}}
- python: run bounded Python for calculations or parsing. action_input: {{"code": "executable Python only"}}
{overdrive_action}
- finish: stop research. action_input must include summary, claims, gaps, used_source_ids, recommended_followups, synthesis_ready.

Rules:
- Use web_search before making strong external factual claims unless enough sources already exist.
- For research/academic questions prefer academic_search over web_search — it queries indexed databases directly.
- Prefer primary/official sources: official docs, project repositories, standards, vendor docs, or maintainer-authored material.
- Use read_page for important sources whose snippets are insufficient; do not finish after reading only one source.
- Use site_map only when you have a specific URL whose broader context or related pages would be valuable.
- Use python only for bounded checks, counting, parsing, or arithmetic.
- Do not repeat equivalent searches or read the same page unless using a different useful mode/query.
- Choose finish only after coverage is broad enough to support a useful report, or when runtime/budgets force synthesis.
- Keep tool inputs compact.
- If context is above 80%, avoid site_map (high output volume). Prefer targeted read_page calls instead.

Finish readiness checklist:
- Do NOT choose finish after a single web_search plus a single read_page.
- Before finish, normally perform at least {minimums["search_before_finish"]} distinct search calls and at least {minimums["read_before_finish"]} read_page calls, unless no budget remains.
- Before finish, read the best available official/primary sources; snippets alone are not enough for a useful report.
- If sources disagree, are low-trust, or are mostly third-party summaries, keep researching or record explicit gaps.
- If the question asks "how to", collect enough implementation detail to produce concrete steps, commands, config examples, and caveats.
- If you choose finish, summarize verified claims and unresolved gaps explicitly in action_input.

Current sources:
{session.compact_sources(max_chars=12000)}

Read artifacts (locators — full content reserved for synthesis):
{session.compact_reads_index()}

Tool trace:
{session.compact_tool_trace(max_chars=8000)}

Reflection summary:
{build_reflection_summary(session)}

Return JSON only matching the requested schema."""


def build_synthesis_prompt(
    session: ResearchSession,
    *,
    clustered_reports: list[str] | None = None,
    compressed_artifacts: str | None = None,
) -> str:
    clustered = "\n\n".join(clustered_reports or [])
    if compressed_artifacts is not None:
        evidence_section = f"Compressed evidence (primary claims extracted per artifact):\n{compressed_artifacts}"
    else:
        evidence_section = f"Read excerpts:\n{session.compact_reads(max_chars=45000)}"
    return f"""Write a source-backed research report in Markdown.

Question:
{session.question}

Working brief:
{session.final_brief}

Sources:
{session.compact_sources(max_chars=30000)}

{evidence_section}

Console outputs:
{chr(10).join(session.console_outputs[-8:]) or "(none)"}

Reflection summary:
{build_reflection_summary(session, max_chars=12000)}

Cluster reports:
{clustered or "(not used)"}

Requirements:
- Cite sources using source ids like [S001].
- Distinguish verified claims from gaps or uncertainty.
- Include a Sources section with id, title, and URL.
- Do not write a thin abstract summary. The report must be useful to someone acting on it.
- Prefer concrete, specific details over generic prose.
- Use the same language as the user's question unless the source material forces a technical term in another language.
- Never claim a source supports something unless that source id appears near the claim.

Report-writing standard:
- Start with a short direct answer: what the user should do or conclude.
- For "how to" questions, include a practical step-by-step section.
- Include commands, file paths, config snippets, YAML/JSON examples, URLs, or parameter names when the sources provide enough evidence.
- Separate server-side setup, client-side setup, validation/testing, troubleshooting, and security/caveats when relevant.
- Explain tradeoffs and prerequisites instead of hiding them.
- If the research found several approaches, compare them and say when each fits.
- If evidence is weak, outdated, third-party-only, or contradictory, say that plainly and list what still needs verification.
- Avoid padding, but do not be terse. A useful technical report is normally several sections, not one short paragraph.
- End with a Sources section listing only sources that were actually useful, plus any lower-quality sources kept for context.
- Return JSON with title, summary, sections, sources."""


def build_compression_prompt(question: str, batch_text: str) -> str:
    return f"""Extract and preserve every primary claim, key finding, concrete fact, number, \
command, configuration value, and caveat from the source excerpts below.
Research question: {question}

Rules:
- Cite every claim with its artifact id in brackets, e.g. [R001].
- Keep commands, file paths, config snippets, URLs, and parameter names verbatim.
- Omit only genuine redundancy (identical claims already stated above).
- Do NOT paraphrase away specifics — precision matters more than brevity.
- Return compressed Markdown only.

Source excerpts:
{batch_text}"""


def build_cluster_prompt(question: str, cluster_name: str, source_text: str) -> str:
    return f"""Summarize this source cluster for final synthesis.

Question:
{question}

Cluster:
{cluster_name}

Sources:
{source_text}

Return Markdown with:
- useful claims and the source ids that support them
- concrete steps, commands, config values, or examples found in the cluster
- contradictions or caveats
- unresolved gaps
- source ids used"""
