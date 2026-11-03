"""Retry policy for transient FirecREST errors.

Adapted from swiss-ai/model-launch (``launchers/utils.py``) so this tool and the
baseline retry exactly like ``sml`` does today; differences in the results then
come from routing, not from a better retry loop.
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

import firecrest as f7t
import httpx

_T = TypeVar("_T")

DEFAULT_DELAYS_SEC: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0)

# 408: FirecREST's own SSH command to the cluster timed out; 429: throttling.
_RETRYABLE_STATUSES = frozenset({408, 429})


def firecrest_status(exc: BaseException) -> int | None:
    """HTTP status of the FirecREST response behind ``exc``, if it carries one."""
    if not isinstance(exc, f7t.UnexpectedStatusException):
        return None
    try:
        return int(exc.responses[-1].status_code)
    except (AttributeError, IndexError, TypeError, ValueError):
        return None


def is_retryable(exc: BaseException) -> bool:
    """Whether a failed FirecREST call may be retried."""
    status = firecrest_status(exc)
    if status is not None:
        return status in _RETRYABLE_STATUSES or 500 <= status < 600
    return isinstance(exc, httpx.HTTPError)


async def with_retry(
    make_call: Callable[[], Awaitable[_T]],
    delays: Sequence[float] = DEFAULT_DELAYS_SEC,
) -> _T:
    """Await ``make_call()``, retrying transient errors after each of ``delays``.

    Not for job submission: FirecREST can report an error for an sbatch that went
    through, so a blind retry may start a second job.
    """
    for delay in delays:
        try:
            return await make_call()
        except Exception as exc:
            if not is_retryable(exc):
                raise
            await asyncio.sleep(delay)
    return await make_call()
