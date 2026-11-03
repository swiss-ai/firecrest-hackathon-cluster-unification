"""Turn FirecREST failures into messages that say what to fix."""

import asyncio

import httpx

from multicluster.profiles import ProfileError
from multicluster.retry import firecrest_status

_STATUS_HINTS = {
    401: "unauthorized: is this cluster's OIDC client the one registered for this instance?",
    403: "forbidden: the OIDC client is not subscribed to this instance, or the account lacks access",
    404: "not found: wrong FirecREST URL or system name for this instance",
    503: "instance unhealthy (503)",
}


def describe_error(exc: BaseException) -> str:
    if isinstance(exc, ProfileError):
        return str(exc)
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "timed out"
    status = firecrest_status(exc)
    if status is not None:
        return _STATUS_HINTS.get(status, f"FirecREST answered {status}")
    if isinstance(exc, httpx.HTTPError):
        return f"unreachable: {type(exc).__name__}"
    return f"{type(exc).__name__}: {exc}"
