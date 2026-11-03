"""Simulated instance flakiness for the mock clusters.

Beverin's FirecREST has been seen answering ``503 ssh service unhealthy`` while
Clariden's was fine. Daint does not misbehave on demand, so a mock cluster can
wrap its client's HTTP transport to answer a share of requests with that 503
instead of sending them. This simulates the *cluster*; it is used by the baseline
and the unified tool alike so their comparison stays fair.
"""

import random
from typing import Any

import httpx

UNHEALTHY_STATUS = 503
UNHEALTHY_BODY = {"message": "ssh service unhealthy (injected by multicluster.faults)"}


class FaultyTransport(httpx.AsyncBaseTransport):
    """Answers a ``rate`` share of requests with a 503 and forwards the rest."""

    def __init__(self, inner: httpx.AsyncBaseTransport, rate: float, rng: random.Random) -> None:
        if not 0.0 <= rate <= 1.0:
            raise ValueError(f"fault rate must be within [0, 1], got {rate}")
        self._inner = inner
        self._rate = rate
        self._rng = rng

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self._rng.random() < self._rate:
            return httpx.Response(UNHEALTHY_STATUS, json=UNHEALTHY_BODY, request=request)
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def install_faults(client: Any, rate: float, seed: int | None = None) -> None:
    """Make a pyfirecrest ``AsyncFirecrest`` client fail a ``rate`` share of requests.

    pyfirecrest replaces its httpx session in ``create_new_session``, so the
    faulty transport is re-applied to every new session as well.
    """
    if rate == 0.0:
        return
    rng = random.Random(seed)  # noqa: S311 - simulation, not cryptography

    def wrap_current_session() -> None:
        session: httpx.AsyncClient = client._session
        session._transport = FaultyTransport(session._transport, rate, rng)

    wrap_current_session()
    original_create_new_session = client.create_new_session

    async def create_new_session_with_faults() -> None:
        await original_create_new_session()
        wrap_current_session()

    client.create_new_session = create_new_session_with_faults
