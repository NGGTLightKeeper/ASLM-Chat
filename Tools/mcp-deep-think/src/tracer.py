# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import json
import logging
import os
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# Trace context
CURRENT_TRACE_ID = ContextVar("current_trace_id", default=None)


# Trace storage

# Capture structured events for one or more active Deep Think runs
class Tracer:
    """Persist structured trace events for debugging and auditing."""

    def __init__(self, log_dir: str = "logs/traces"):
        """Prepare the trace output directory and in-memory trace store."""

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.log_dir = os.path.join(base_dir, log_dir)

        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        self._active_traces: dict[str, dict[str, Any]] = {}


    # Trace lifecycle
    def start_trace(self, query: str) -> str:
        """Start a new trace session and return its id."""

        trace_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:8]

        self._active_traces[trace_id] = {
            "id": trace_id,
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "events": [],
        }

        CURRENT_TRACE_ID.set(trace_id)
        logger.info("Started trace: %s", trace_id)
        return trace_id

    def end_trace(self, trace_id: str | None = None, result: Any = None):
        """Finalize an active trace and save it to disk."""

        trace_id = trace_id or CURRENT_TRACE_ID.get()
        if not trace_id or trace_id not in self._active_traces:
            return

        trace_data = self._active_traces[trace_id]
        trace_data["end_timestamp"] = datetime.now().isoformat()
        trace_data["result"] = result

        filename = os.path.join(self.log_dir, f"trace_{trace_id}.json")
        try:
            with open(filename, "w", encoding="utf-8") as handle:
                json.dump(trace_data, handle, indent=2, ensure_ascii=False)
            logger.info("Trace saved to: %s", filename)
        except Exception as exc:
            logger.error("Failed to save trace: %s", exc)

        del self._active_traces[trace_id]


    # Event logging
    def log(self, source: str, event_type: str, data: Any, trace_id: str | None = None):
        """Append an event to the current trace when one is active."""

        trace_id = trace_id or CURRENT_TRACE_ID.get()
        if not trace_id or trace_id not in self._active_traces:
            logger.debug("[Trace ignored] %s - %s: %s", source, event_type, str(data)[:100])
            return

        event = {
            "time": time.time(),
            "source": source,
            "type": event_type,
            "data": data,
        }
        self._active_traces[trace_id]["events"].append(event)

        # Mirror important events into the regular logger for immediate visibility.
        if event_type == "error":
            logger.error("[%s] %s", source, data)
        elif event_type == "llm_request":
            logger.info("[%s] Asking LLM...", source)


# Singleton instance
tracer = Tracer()
