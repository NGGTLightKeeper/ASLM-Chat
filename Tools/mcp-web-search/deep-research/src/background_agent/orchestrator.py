# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger("background_agent.orchestrator")


# Task state models.
# Task lifecycle enum.
class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


# In-memory record for one background task.
@dataclass
class TaskHandle:
    """Internal state stored for one orchestrated task."""

    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Any = None
    error: Optional[str] = None
    progress: str = ""
    ready_event: asyncio.Event = field(default_factory=asyncio.Event)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    _asyncio_task: Optional[asyncio.Task] = field(default=None, repr=False)


# Task orchestrator.
# Background task orchestrator.
class TaskOrchestrator:
    # Configure task concurrency limits.
    def __init__(self, max_concurrent: int = 4):
        self._tasks: Dict[str, TaskHandle] = {}
        self._sem = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()

    # Submit a new task for background execution.
    async def submit(
        self,
        fn: Callable[..., Awaitable[Any]],
        *args,
        task_id: Optional[str] = None,
        max_retries: int = 2,
        retry_base_delay: float = 5.0,
        **kwargs,
    ) -> str:
        """Start a task in the background and return its id immediately."""

        task_id = task_id or uuid.uuid4().hex[:12]
        handle = TaskHandle(task_id=task_id)
        async with self._lock:
            self._tasks[task_id] = handle

        # Execute the task with retries under the shared semaphore.
        async def _runner():
            async with self._sem:
                handle.status = TaskStatus.RUNNING
                handle.started_at = time.time()
                handle.progress = "Started"

                for attempt in range(max_retries + 1):
                    if handle.cancel_event.is_set():
                        handle.status = TaskStatus.CANCELLED
                        handle.finished_at = time.time()
                        return

                    try:
                        handle.progress = f"Attempt {attempt + 1}/{max_retries + 1}"
                        result = await fn(*args, **kwargs)
                        handle.result = result
                        handle.status = TaskStatus.DONE
                        handle.progress = "Done"
                        handle.finished_at = time.time()
                        handle.ready_event.set()
                        logger.info(
                            f"Task {task_id} completed in "
                            f"{handle.finished_at - handle.started_at:.1f}s"
                        )
                        return
                    except asyncio.CancelledError:
                        handle.status = TaskStatus.CANCELLED
                        handle.finished_at = time.time()
                        return
                    except Exception as error:
                        logger.warning(
                            f"Task {task_id} attempt {attempt + 1} failed: "
                            f"{type(error).__name__}: {error}"
                        )
                        if attempt < max_retries:
                            delay = retry_base_delay * (2 ** attempt)
                            handle.progress = f"Retry {attempt + 1} after {delay:.0f}s"
                            await asyncio.sleep(delay)
                        else:
                            handle.status = TaskStatus.FAILED
                            handle.error = f"{type(error).__name__}: {error}"
                            handle.finished_at = time.time()
                            handle.ready_event.set()
                            logger.error(f"Task {task_id} permanently failed: {error}")

        asyncio_task = asyncio.create_task(_runner(), name=f"research_{task_id}")
        handle._asyncio_task = asyncio_task
        logger.info(f"Task {task_id} submitted")
        return task_id

    # Wait for a task to finish or time out.
    async def wait_ready(
        self,
        task_id: str,
        timeout: float = 660.0,
    ) -> TaskStatus:
        """Wait for a task to reach a final state or timeout."""

        handle = self._tasks.get(task_id)
        if not handle:
            raise KeyError(f"Unknown task: {task_id}")

        try:
            await asyncio.wait_for(handle.ready_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Task {task_id} wait timeout after {timeout}s")

        return handle.status

    # Return a public task status snapshot.
    def get_status(self, task_id: str) -> Optional[Dict]:
        """Return the current public status snapshot for a task."""

        handle = self._tasks.get(task_id)
        if not handle:
            return None
        elapsed = (
            (handle.finished_at or time.time()) - handle.started_at
            if handle.started_at
            else 0.0
        )
        return {
            "task_id": task_id,
            "status": handle.status.value,
            "progress": handle.progress,
            "elapsed_sec": round(elapsed, 1),
            "error": handle.error,
        }

    # Return the stored task result.
    def get_result(self, task_id: str) -> Any:
        """Return the completed result for a task, if any."""

        handle = self._tasks.get(task_id)
        return handle.result if handle else None

    # Cancel a running task.
    def cancel(self, task_id: str) -> bool:
        """Cancel a running task if it exists."""

        handle = self._tasks.get(task_id)
        if not handle:
            return False
        handle.cancel_event.set()
        if handle._asyncio_task and not handle._asyncio_task.done():
            handle._asyncio_task.cancel()
        return True

    # Remove old finished tasks from memory.
    def cleanup_old_tasks(self, max_age_sec: float = 3600.0) -> int:
        """Remove finished task records older than the requested age."""

        now = time.time()
        to_remove = [
            task_id
            for task_id, handle in self._tasks.items()
            if handle.finished_at and now - handle.finished_at > max_age_sec
        ]
        for task_id in to_remove:
            del self._tasks[task_id]
        return len(to_remove)

    # Return the count of currently running tasks.
    @property
    def active_count(self) -> int:
        """Return the number of tasks currently in the running state."""

        return sum(
            1 for handle in self._tasks.values()
            if handle.status == TaskStatus.RUNNING
        )
