"""
Shared fire-and-forget async task launcher with reference tracking.

Prevents two known issues with raw asyncio.create_task():
1. GC silently cancelling tasks when no strong reference is held.
2. Unlogged exceptions swallowed as "Task exception was never retrieved".

Usage:
    from app.core.background_task_utils import fire_and_forget

    fire_and_forget(
        some_async_call(),
        name="cache_warm_history",
    )

NOTE (future improvement): On graceful shutdown, in-flight tasks in
_background_tasks are not awaited or cancelled. If this becomes important
(e.g. preventing half-written Redis state), add the following to your
FastAPI lifespan shutdown handler:

    from app.core.background_task_utils import drain_background_tasks
    await drain_background_tasks()
"""
from __future__ import annotations

import asyncio
import logging
from typing import Coroutine, Any

logger = logging.getLogger(__name__)

# Module-level set: holds strong references to all in-flight tasks,
# shared across all instances/requests in the same process.
_background_tasks: set[asyncio.Task] = set()


def fire_and_forget(coro: Coroutine[Any, Any, Any], *, name: str = "background") -> asyncio.Task:
    """
    Launch a coroutine as a tracked background task.

    The returned Task is kept alive in a module-level set until completion,
    preventing the garbage collector from silently cancelling it.
    Any unhandled exception is logged via structured logging.
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    task.add_done_callback(_log_task_exception)
    return task


def _log_task_exception(task: asyncio.Task) -> None:
    """Log any unhandled exception from a completed background task."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error(
            "background_task_failed",
            extra={"task_name": task.get_name(), "error": str(exc)},
            exc_info=exc,
        )


async def drain_background_tasks(timeout: float = 5.0) -> None:
    """
    Await all in-flight background tasks (for graceful shutdown).

    Call this from your FastAPI lifespan shutdown handler if you need
    to ensure all pending writes complete before the process exits.
    """
    if not _background_tasks:
        return
    logger.info("draining_background_tasks", extra={"count": len(_background_tasks)})
    done, pending = await asyncio.wait(_background_tasks, timeout=timeout)
    for task in pending:
        task.cancel()
    if pending:
        # Actually await cancellation so CancelledError propagates before
        # the event loop shuts down (prevents "Task was destroyed but pending").
        await asyncio.gather(*pending, return_exceptions=True)
    logger.info("background_tasks_drained", extra={"completed": len(done), "cancelled": len(pending)})
