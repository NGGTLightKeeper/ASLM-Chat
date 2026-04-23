# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Agentic deep research orchestration."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from core.llm.llm_client import call_llm_json
from services.deep_research.artifacts import persist_run_artifacts
from services.deep_research.config import ResearchConfig
from services.deep_research.models import AgentDecision, ResearchBrief, ResearchSession, ToolTrace
from services.deep_research.prompts import build_controller_prompt, decision_schema
from services.deep_research.runtime_logging import DeepResearchRunLogger
from services.deep_research.synthesis import synthesize_report
from services.deep_research.tools import run_agent_python, run_agent_read_page, run_agent_web_search
from services.deep_research.tools.base import summarize_text


def _coerce_decision(payload: object, *, overdrive: bool = False) -> AgentDecision | None:
    if not isinstance(payload, dict):
        return None
    action = str(payload.get("action") or "").strip()
    if action == "linux_sandbox":
        action = "python"
    allowed_actions = {"reflect", "web_search", "academic_search", "read_page", "site_map", "python", "finish"}
    if overdrive:
        allowed_actions.add("import_web_file")
    if action not in allowed_actions:
        return None
    action_input = payload.get("action_input")
    if not isinstance(action_input, dict):
        raw_input = str(action_input or "").strip()
        if action == "web_search":
            action_input = {"query": raw_input}
        elif action == "academic_search":
            action_input = {"query": raw_input}
        elif action == "read_page":
            action_input = {"source": raw_input}
        elif action == "site_map":
            action_input = {"url": raw_input, "topic": ""}
        elif action == "import_web_file":
            action_input = {"url": raw_input}
        elif action == "python":
            action_input = {"code": raw_input}
        elif action == "finish":
            action_input = {"summary": raw_input}
        else:
            action_input = {}
    try:
        raw_confidence = payload.get("confidence", 0.5)
        if isinstance(raw_confidence, str) and raw_confidence.strip().endswith("%"):
            confidence = float(raw_confidence.strip().rstrip("%")) / 100.0
        else:
            confidence = float(raw_confidence)
    except Exception:
        confidence = 0.5
    return AgentDecision(
        thought=str(payload.get("thought") or action),
        action=action,  # type: ignore[arg-type]
        action_input=action_input,
        confidence=max(0.0, min(1.0, confidence)),
    )


def _fallback_decision(session: ResearchSession, step: int) -> AgentDecision:
    if session.search_calls < int(session.config.max_search_calls) and not session.source_pool:
        return AgentDecision(
            thought="No sources have been collected yet; run an initial search.",
            action="web_search",
            action_input={"query": session.question},
            confidence=0.2,
        )
    unread = [source for source in session.source_pool if not source.read_artifact_ids]
    if session.read_calls < int(session.config.max_read_calls) and unread:
        return AgentDecision(
            thought="Read the best unread source before synthesis.",
            action="read_page",
            action_input={"source": unread[0].id, "mode": "summary_stub"},
            confidence=0.2,
        )
    return AgentDecision(
        thought="Fallback controller has enough material or no useful tool remains.",
        action="finish",
        action_input={
            "summary": "Research completed with the available sources.",
            "used_source_ids": [source.id for source in session.source_pool],
            "synthesis_ready": True,
        },
        confidence=0.2,
    )


def _runtime_log(session: ResearchSession) -> DeepResearchRunLogger | None:
    logger = getattr(session, "runtime_logger", None)
    return logger if isinstance(logger, DeepResearchRunLogger) else None


def _remaining_budgets(session: ResearchSession) -> dict[str, int]:
    cfg = session.config
    return {
        "web_search": max(0, int(cfg.max_search_calls) + session.extra_search_quota - session.search_calls),
        "academic_search": max(0, int(cfg.max_search_calls) + session.extra_search_quota - session.search_calls),
        "read_page": max(0, int(cfg.max_read_calls) + session.extra_read_quota - session.read_calls),
        "site_map": max(0, int(getattr(cfg, "max_site_map_calls", 4)) - session.site_map_calls),
        "python": max(0, int(cfg.max_python_calls) - session.python_calls),
        "import_web_file": 1 if _budget_allows(session, "import_web_file") else 0,
    }


def _session_snapshot(session: ResearchSession) -> dict[str, Any]:
    return {
        "elapsed_sec": round(session.elapsed, 2),
        "context_chars": session.context_size_estimate(),
        "sources": len(session.source_pool),
        "read_artifacts": len(session.read_artifacts),
        "tool_calls": len(session.tool_trace),
        "reflect_streak": session.reflect_streak,
        "remaining": _remaining_budgets(session),
    }


def _log_session_event(session: ResearchSession, name: str, **payload: Any) -> None:
    logger = _runtime_log(session)
    if logger is None:
        return
    logger.event(name, **payload)


async def _ask_controller(session: ResearchSession, step: int) -> AgentDecision:
    prompt = build_controller_prompt(session, step)
    try:
        overdrive_mode = getattr(session, "sandbox", None) is not None
        payload = await call_llm_json(
            prompt=prompt,
            model=session.config.query_model,
            temperature=float(session.config.controller_temperature),
            json_schema=decision_schema(overdrive=overdrive_mode),
            schema_name="deep_research_controller_action",
            structured_output=bool(session.config.structured_output_enabled),
            strict=bool(session.config.structured_output_strict),
            timeout=float(session.config.controller_timeout_sec),
            debug_label="deep_research_controller",
        )
        decision = _coerce_decision(payload, overdrive=overdrive_mode)
        if decision is None:
            fallback = _fallback_decision(session, step)
            _log_session_event(
                session,
                "controller_invalid_payload",
                step=step,
                payload_summary=summarize_text(str(payload), 600),
                fallback_action=fallback.action,
                snapshot=_session_snapshot(session),
            )
            return fallback
        _log_session_event(
            session,
            "controller_decision",
            step=step,
            action=decision.action,
            confidence=round(float(decision.confidence), 3),
            thought=summarize_text(decision.thought, 400),
            action_input=decision.action_input,
            snapshot=_session_snapshot(session),
        )
        return decision
    except Exception as exc:
        session.errors.append(f"Controller failed: {type(exc).__name__}: {exc}")
        fallback = _fallback_decision(session, step)
        _log_session_event(
            session,
            "controller_error",
            step=step,
            error=f"{type(exc).__name__}: {exc}",
            fallback_action=fallback.action,
            snapshot=_session_snapshot(session),
        )
        return fallback


def _record_reflection(session: ResearchSession, decision: AgentDecision, step: int) -> None:
    payload = decision.action_input
    claim_items = payload.get("claims", [])
    if not isinstance(claim_items, list):
        claim_items = []
    gap_items = payload.get("gaps", [])
    if not isinstance(gap_items, list):
        gap_items = []
    for claim in claim_items:
        text = str(claim).strip()
        if text and text not in session.claims:
            session.claims.append(text)
    for gap in gap_items:
        text = str(gap).strip()
        if text and text not in session.gaps:
            session.gaps.append(text)
    session.reflection_log.append(decision.thought)

    if payload.get("request_extra_quota") and not session.extra_quota_used:
        grant_msg = _grant_extra_quota(session)
        session.reflection_log.append(grant_msg)
        _log_session_event(
            session,
            "extra_quota_granted",
            step=step,
            message=grant_msg,
            snapshot=_session_snapshot(session),
        )

    session.add_trace(
        ToolTrace(
            step=step,
            action="reflect",
            input=payload,
            status="success",
            output_summary=summarize_text(decision.thought, 500),
        )
    )


def _list_input(payload: dict[str, Any], key: str) -> list[str]:
    for candidate in (key, f"{key}_"):
        value = payload.get(candidate)
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
    return []


def _bool_input(payload: dict[str, Any], key: str, default: bool) -> bool:
    for candidate in (key, f"{key}_"):
        value = payload.get(candidate)
        if isinstance(value, bool):
            return value
    return default


def _finish(session: ResearchSession, decision: AgentDecision) -> None:
    payload = decision.action_input
    claims = _list_input(payload, "claims")
    gaps = _list_input(payload, "gaps")
    used = _list_input(payload, "used_source_ids") or [source.id for source in session.source_pool]
    followups = _list_input(payload, "recommended_followups")
    for claim in claims:
        if claim and claim not in session.claims:
            session.claims.append(claim)
    for gap in gaps:
        if gap and gap not in session.gaps:
            session.gaps.append(gap)
    session.final_brief = ResearchBrief(
        summary=str(payload.get("summary") or decision.thought),
        claims=claims or list(session.claims),
        gaps=gaps or list(session.gaps),
        used_source_ids=used,
        recommended_followups=followups,
        synthesis_ready=_bool_input(payload, "synthesis_ready", True),
    )
    _log_session_event(
        session,
        "finish_selected",
        summary=summarize_text(session.final_brief.summary, 400),
        used_source_ids=list(session.final_brief.used_source_ids),
        claims=len(session.final_brief.claims),
        gaps=len(session.final_brief.gaps),
        snapshot=_session_snapshot(session),
    )


def _effective_deadline(session: ResearchSession) -> float:
    """Deadline for tool use that adapts synthesis reserve to current context size."""
    cfg = session.config
    total = max(1.0, float(cfg.total_timeout_sec))
    base_reserve = max(30.0, float(cfg.synthesis_reserve_sec))

    # Scale reserve: small context → 60 % of base, full context → 100 % of base.
    # A large context triggers source clustering in synthesize_report(), which adds
    # one extra round of LLM calls before the main synthesis pass.
    context_ratio = min(1.0, session.context_size_estimate() / max(1, int(cfg.synthesis_context_budget)))
    reserve = min(total * 0.5, base_reserve * (0.6 + 0.4 * context_ratio))

    floor = 60.0 if total >= 120.0 else max(1.0, total * 0.5)
    return max(floor, total - reserve)


def _budget_allows(session: ResearchSession, action: str) -> bool:
    cfg = session.config
    if action == "web_search":
        if session.search_calls >= int(cfg.max_search_calls) + session.extra_search_quota:
            return False
        # Block new searches when context is nearly full (> 90% of effective budget)
        ctx = session.context_size_estimate()
        if ctx >= int(cfg.effective_tool_context_budget * 0.90):
            return False
        return True
    if action == "read_page":
        if session.read_calls >= int(cfg.max_read_calls) + session.extra_read_quota:
            return False
        # Block reads when context is full (> 95% — reads are larger, stricter cap)
        ctx = session.context_size_estimate()
        if ctx >= int(cfg.effective_tool_context_budget * 0.95):
            return False
        return True
    if action == "academic_search":
        if session.search_calls >= int(cfg.max_search_calls) + session.extra_search_quota:
            return False
        ctx = session.context_size_estimate()
        if ctx >= int(cfg.effective_tool_context_budget * 0.90):
            return False
        return True
    if action == "site_map":
        if session.site_map_calls >= int(getattr(cfg, "max_site_map_calls", 4)):
            return False
        ctx = session.context_size_estimate()
        if ctx >= int(cfg.effective_tool_context_budget * 0.85):
            return False
        return True
    if action in {"python", "linux_sandbox"}:
        return session.python_calls < int(cfg.max_python_calls) and str(cfg.python_backend).lower() not in {"disabled", "none", "off"}
    if action == "import_web_file":
        sandbox = getattr(session, "sandbox", None)
        settings = getattr(session, "overdrive_settings", None)
        return (
            sandbox is not None
            and getattr(sandbox, "running", False)
            and getattr(settings, "import_file_enabled", False)
        )
    return True


def _grant_extra_quota(session: ResearchSession) -> str:
    """Grant a one-time quota extension and return a log message."""
    cfg = session.config
    session.extra_quota_used = True
    session.extra_search_quota = int(getattr(cfg, "extra_quota_search_calls", 7))
    session.extra_read_quota = int(getattr(cfg, "extra_quota_read_calls", 7))
    return (
        f"Extra quota granted: +{session.extra_search_quota} web_search, "
        f"+{session.extra_read_quota} read_page."
    )


def _forced_evidence_decision(session: ResearchSession, confidence: float) -> AgentDecision | None:
    cfg = session.config
    if session.search_calls < int(getattr(cfg, "min_search_calls_before_finish", 0)) and _budget_allows(session, "web_search"):
        gap_query = session.gaps[0] if session.gaps else session.question
        return AgentDecision(
            thought="Finish deferred: run another search to broaden coverage before synthesis.",
            action="web_search",
            action_input={"query": gap_query},
            confidence=min(confidence, 0.5),
        )

    unread = sorted(
        [source for source in session.source_pool if not source.read_artifact_ids],
        key=lambda source: (str(source.trust_tier or "?") not in {"A", "B"}, -float(source.score or 0.0), source.id),
    )
    if session.read_calls < int(getattr(cfg, "min_read_calls_before_finish", 0)) and unread and _budget_allows(session, "read_page"):
        return AgentDecision(
            thought="Finish deferred: read more sources before synthesis.",
            action="read_page",
            action_input={"source": unread[0].id, "mode": "summary_stub"},
            confidence=min(confidence, 0.5),
        )
    return None


async def _execute_decision(session: ResearchSession, decision: AgentDecision, step: int) -> bool:
    """Execute one decision. Return True when the loop should finish."""

    action = decision.action
    if not _budget_allows(session, action):
        session.reflection_log.append(f"Budget blocked action {action}: {decision.thought}")
        _log_session_event(
            session,
            "budget_blocked",
            step=step,
            requested_action=action,
            thought=summarize_text(decision.thought, 300),
            snapshot=_session_snapshot(session),
        )
        action = "reflect"

    if action == "reflect":
        session.reflect_streak += 1
        _record_reflection(session, decision, step)
        _log_session_event(
            session,
            "reflection_recorded",
            step=step,
            thought=summarize_text(decision.thought, 400),
            action_input=decision.action_input,
            snapshot=_session_snapshot(session),
        )
        if session.reflect_streak > int(session.config.max_reflect_without_tool):
            if _budget_allows(session, "web_search"):
                forced = AgentDecision(
                    thought="Forced search after repeated reflection.",
                    action="web_search",
                    action_input={"query": session.question},
                    confidence=decision.confidence,
                )
                return await _execute_decision(session, forced, step)
        return False

    session.reflect_streak = 0
    start = time.time()
    payload: dict[str, Any] = dict(decision.action_input)
    _log_session_event(
        session,
        "tool_started",
        step=step,
        action=action,
        action_input=payload,
        snapshot=_session_snapshot(session),
    )
    try:
        if action == "finish" and not session.source_pool and _budget_allows(session, "web_search"):
            forced = AgentDecision(
                thought="Finish deferred because no sources have been collected.",
                action="web_search",
                action_input={"query": session.question},
                confidence=min(decision.confidence, 0.5),
            )
            return await _execute_decision(session, forced, step)
        if action == "finish":
            forced = _forced_evidence_decision(session, decision.confidence)
            if forced is not None:
                session.reflection_log.append(forced.thought)
                return await _execute_decision(session, forced, step)
        if action == "web_search":
            query = str(payload.get("query") or session.question).strip()
            output = await run_agent_web_search(session, query)
        elif action == "academic_search":
            from services.deep_research.tools.academic import run_agent_academic_search
            query = str(payload.get("query") or session.question).strip()
            domains = payload.get("domains") if isinstance(payload.get("domains"), list) else None
            output = await run_agent_academic_search(session, query, target_domains=domains)
        elif action == "read_page":
            output = await run_agent_read_page(
                session,
                source=str(payload.get("source") or ""),
                mode=str(payload.get("mode") or "full"),
                query=str(payload.get("query") or ""),
            )
        elif action == "site_map":
            from services.deep_research.tools.site_mapper import run_agent_site_map
            url = str(payload.get("url") or "").strip()
            topic = str(payload.get("topic") or session.question).strip()
            if not url:
                output = "site_map requires a url in action_input."
            else:
                output = await run_agent_site_map(session, url, topic)
        elif action == "python":
            output = await run_agent_python(session, str(payload.get("code") or ""))
        elif action == "import_web_file":
            from services.deep_research.tools.import_web_file import run_agent_import_web_file
            output = await run_agent_import_web_file(
                session,
                url=str(payload.get("url") or ""),
                filename=str(payload.get("filename") or ""),
            )
        elif action == "finish":
            _finish(session, decision)
            return True
        else:
            output = f"Unsupported action: {action}"
        session.add_trace(
            ToolTrace(
                step=step,
                action=action,
                input=payload,
                status="success",
                output_summary=summarize_text(output, 1000),
                elapsed_ms=int((time.time() - start) * 1000),
            )
        )
        _log_session_event(
            session,
            "tool_completed",
            step=step,
            action=action,
            status="success",
            elapsed_ms=int((time.time() - start) * 1000),
            output_summary=summarize_text(output, 800),
            snapshot=_session_snapshot(session),
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        session.errors.append(message)
        session.add_trace(
            ToolTrace(
                step=step,
                action=action,
                input=payload,
                status="error",
                output_summary=message,
                elapsed_ms=int((time.time() - start) * 1000),
            )
        )
        _log_session_event(
            session,
            "tool_completed",
            step=step,
            action=action,
            status="error",
            elapsed_ms=int((time.time() - start) * 1000),
            error=message,
            snapshot=_session_snapshot(session),
        )
    return False


async def orchestrate(question: str, depth: str = "standard", total_timeout_sec: float | None = None) -> str:
    import logging as _logging
    _orch_log = _logging.getLogger("services.deep_research.orchestrator")

    overdrive = (depth or "standard").strip().lower() == "overdrive"
    if overdrive:
        from services.deep_research.overdrive_config import load_overdrive_config
        cfg, od_settings = load_overdrive_config(question)
    else:
        cfg = ResearchConfig.for_question(question, depth)
        od_settings = None

    if total_timeout_sec is not None:
        cfg.total_timeout_sec = float(total_timeout_sec)
        cfg.synthesis_reserve_sec = min(
            float(cfg.synthesis_reserve_sec),
            max(30.0, float(cfg.total_timeout_sec) * 0.25),
        )

    session = ResearchSession(question=question.strip(), config=cfg, overdrive_settings=od_settings)
    run_logger = None
    if bool(getattr(cfg, "write_logs", True)):
        try:
            run_logger = DeepResearchRunLogger(session.question, cfg.depth)
            session.runtime_logger = run_logger
            _log_session_event(
                session,
                "session_configured",
                depth=cfg.depth,
                content_type=getattr(cfg, "content_type", "general"),
                total_timeout_sec=float(cfg.total_timeout_sec),
                synthesis_reserve_sec=float(cfg.synthesis_reserve_sec),
                controller_timeout_sec=float(cfg.controller_timeout_sec),
                max_steps=int(cfg.max_steps),
                max_search_calls=int(cfg.max_search_calls),
                max_read_calls=int(cfg.max_read_calls),
                max_python_calls=int(cfg.max_python_calls),
                max_site_map_calls=int(getattr(cfg, "max_site_map_calls", 4)),
                effective_tool_context_budget=int(cfg.effective_tool_context_budget),
            )
        except Exception as exc:
            _orch_log.warning("Failed to initialize deep research runtime log: %s", exc)
            run_logger = None

    # Adapt synthesis_context_budget to the model's actual loaded context window.
    try:
        from core.llm.llm_client import get_active_model_info
        model_info = await get_active_model_info()
        loaded_ctx = int(model_info.get("loaded_context_length") or 0)
        if loaded_ctx > 0:
            # Reserve ~30% of loaded context for the model's own reasoning and overhead.
            usable = int(loaded_ctx * 0.70)
            if usable < cfg.synthesis_context_budget:
                cfg.synthesis_context_budget = usable
            # Cap read_page_max_chars at 20% of loaded context to keep pages manageable.
            page_cap = int(loaded_ctx * 0.20)
            if page_cap < cfg.read_page_max_chars:
                cfg.read_page_max_chars = max(8_000, page_cap)
            import logging as _log
            _log.getLogger("services.deep_research.orchestrator").info(
                "Model context: loaded=%d usable=%d → synthesis_context_budget=%d read_page_max_chars=%d model=%s",
                loaded_ctx, usable, cfg.synthesis_context_budget, cfg.read_page_max_chars,
                model_info.get("id", "?"),
            )
            _log_session_event(
                session,
                "model_context_loaded",
                loaded_context_length=loaded_ctx,
                usable_context=usable,
                synthesis_context_budget=int(cfg.synthesis_context_budget),
                read_page_max_chars=int(cfg.read_page_max_chars),
                model_id=model_info.get("id", "?"),
            )
    except Exception:
        pass

    # Start ephemeral sandbox for overdrive mode
    sandbox = None
    if overdrive and od_settings is not None and od_settings.sandbox_enabled:
        try:
            from services.deep_research.backends.ephemeral_sandbox import EphemeralSandbox
            sandbox = EphemeralSandbox(
                image=od_settings.sandbox_image,
                cpu=od_settings.sandbox_cpu,
                memory=od_settings.sandbox_memory,
                memory_swap=od_settings.sandbox_memory_swap,
                pids_limit=od_settings.sandbox_pids_limit,
            )
            await sandbox.start()
            session.sandbox = sandbox
            _orch_log.info("Overdrive sandbox started: %s", sandbox.container_name)
            _log_session_event(
                session,
                "sandbox_started",
                container_name=getattr(sandbox, "container_name", ""),
            )
        except Exception as exc:
            _orch_log.warning("Failed to start overdrive sandbox: %s — continuing without it", exc)
            _log_session_event(
                session,
                "sandbox_start_failed",
                error=f"{type(exc).__name__}: {exc}",
            )
            sandbox = None

    try:
        for step in range(1, int(cfg.max_steps) + 1):
            _log_session_event(
                session,
                "step_started",
                step=step,
                snapshot=_session_snapshot(session),
            )
            if session.elapsed >= _effective_deadline(session):
                session.errors.append("Research deadline reached; starting synthesis with available context.")
                _log_session_event(
                    session,
                    "deadline_reached",
                    step=step,
                    snapshot=_session_snapshot(session),
                )
                break
            ctx = session.context_size_estimate()
            if ctx >= cfg.effective_tool_context_budget:
                session.errors.append(
                    f"Context budget reached ({ctx:,} / {cfg.effective_tool_context_budget:,} chars); "
                    "starting synthesis."
                )
                _log_session_event(
                    session,
                    "context_budget_reached",
                    step=step,
                    context_chars=ctx,
                    effective_tool_context_budget=int(cfg.effective_tool_context_budget),
                    snapshot=_session_snapshot(session),
                )
                break
            decision = await _ask_controller(session, step)
            done = await _execute_decision(session, decision, step)
            if done:
                break

        if session.final_brief is None:
            _finish(session, _fallback_decision(session, int(cfg.max_steps) + 1))

        _log_session_event(
            session,
            "synthesis_started",
            snapshot=_session_snapshot(session),
        )
        report = await synthesize_report(session)
        _log_session_event(
            session,
            "synthesis_completed",
            report_chars=len(report),
            errors=len(session.errors),
            snapshot=_session_snapshot(session),
        )
        if bool(getattr(cfg, "write_logs", True)) and "PYTEST_CURRENT_TEST" not in os.environ:
            try:
                artifact_dir = persist_run_artifacts(session, report)
                _log_session_event(
                    session,
                    "artifacts_persisted",
                    path=str(artifact_dir),
                )
            except Exception as exc:
                session.errors.append(f"Log persistence failed: {type(exc).__name__}: {exc}")
                _log_session_event(
                    session,
                    "artifacts_persist_failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
        return report
    finally:
        if sandbox is not None:
            try:
                await sandbox.stop()
                _log_session_event(
                    session,
                    "sandbox_stopped",
                    container_name=getattr(sandbox, "container_name", ""),
                )
            finally:
                if run_logger is not None:
                    run_logger.close()
        elif run_logger is not None:
            run_logger.close()


async def run_deep_research(
    question: str,
    depth: str = "standard",
    hard_timeout: float | None = None,
) -> str:
    cfg = ResearchConfig.for_depth(depth)
    timeout = hard_timeout or cfg.total_timeout_sec
    try:
        return await asyncio.wait_for(orchestrate(question, depth, total_timeout_sec=timeout), timeout=timeout)
    except asyncio.TimeoutError:
        return f"# Research: {question}\n\nPipeline timed out after {timeout:.0f}s (depth={depth}).\n"
    finally:
        try:
            from services.web_search import shutdown_web_search

            await shutdown_web_search()
        except Exception:
            pass
