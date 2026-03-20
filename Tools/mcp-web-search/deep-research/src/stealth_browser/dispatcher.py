# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import logging
from typing import Awaitable, Callable, List, Optional, TypeVar

logger = logging.getLogger("stealth.dispatcher")

T = TypeVar("T")


# Memory helpers.
# Read current RAM usage.
def _get_memory_percent() -> float:
    """Return current system RAM usage as a percentage."""

    try:
        import psutil

        return psutil.virtual_memory().percent
    except ImportError:
        return 50.0


# Adaptive dispatchers.
# Dispatcher that reacts to memory pressure.
class MemoryAdaptiveDispatcher:
    # Configure adaptive concurrency limits.
    def __init__(
        self,
        max_concurrency: int = 8,
        memory_threshold_percent: float = 85.0,
        check_interval_sec: float = 1.0,
        backoff_sec: float = 3.0,
    ):
        self.max_concurrency = max_concurrency
        self.memory_threshold = memory_threshold_percent
        self.check_interval = check_interval_sec
        self.backoff_sec = backoff_sec
        self._active_count = 0
        self._lock = asyncio.Lock()

    # Wait until memory pressure drops.
    async def _wait_for_memory(self) -> None:
        """Pause task launches while RAM usage stays above the threshold."""

        while True:
            memory_percent = _get_memory_percent()
            if memory_percent < self.memory_threshold:
                return
            logger.warning(
                f"Memory {memory_percent:.1f}% > threshold {self.memory_threshold}% "
                f"waiting {self.backoff_sec}s before launching a new task"
            )
            await asyncio.sleep(self.backoff_sec)

    # Reserve one worker slot.
    async def _acquire(self) -> None:
        """Wait for both a free slot and acceptable memory pressure."""

        while True:
            await self._wait_for_memory()
            async with self._lock:
                if self._active_count < self.max_concurrency:
                    self._active_count += 1
                    return
            await asyncio.sleep(self.check_interval)

    # Release one worker slot.
    async def _release(self) -> None:
        """Release one active worker slot."""

        async with self._lock:
            self._active_count -= 1

    # Run a batch with adaptive concurrency.
    async def run(
        self,
        items: List,
        worker: Callable[..., Awaitable[T]],
        **kwargs,
    ) -> List[Optional[T]]:
        """Run one async worker per item under adaptive concurrency limits."""

        results: List[Optional[T]] = [None] * len(items)

        # Run one item and store its result.
        async def _run_one(index: int, item) -> None:
            await self._acquire()
            try:
                results[index] = await worker(item, **kwargs)
            except Exception as error:
                logger.warning(f"Worker error for item {index}: {error}")
                results[index] = None
            finally:
                await self._release()

        tasks = [_run_one(index, item) for index, item in enumerate(items)]
        await asyncio.gather(*tasks)
        return results

    # Expose the active worker count.
    @property
    def active_tasks(self) -> int:
        """Return the number of currently active worker tasks."""

        return self._active_count


# Fixed-capacity dispatcher.
class SemaphoreDispatcher:
    # Configure the semaphore limit.
    def __init__(self, max_concurrency: int = 5):
        self.max_concurrency = max_concurrency
        self._sem = asyncio.Semaphore(max_concurrency)

    # Run a batch under a semaphore limit.
    async def run(
        self,
        items: List,
        worker: Callable[..., Awaitable[T]],
        **kwargs,
    ) -> List[Optional[T]]:
        """Run one async worker per item with a fixed concurrency limit."""

        results: List[Optional[T]] = [None] * len(items)

        # Run one item under the semaphore.
        async def _run_one(index: int, item) -> None:
            async with self._sem:
                try:
                    results[index] = await worker(item, **kwargs)
                except Exception as error:
                    logger.warning(f"Worker error for item {index}: {error}")
                    results[index] = None

        tasks = [_run_one(index, item) for index, item in enumerate(items)]
        await asyncio.gather(*tasks)
        return results
