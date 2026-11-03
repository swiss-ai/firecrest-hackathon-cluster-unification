import random

import httpx
import pytest

from multicluster.faults import UNHEALTHY_STATUS, FaultyTransport, install_faults


def _ok_transport() -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))


async def _status_of(transport: httpx.AsyncBaseTransport) -> int:
    async with httpx.AsyncClient(transport=transport, base_url="https://f7t.test") as client:
        return (await client.get("/status")).status_code


async def test_rate_zero_forwards_every_request() -> None:
    transport = FaultyTransport(_ok_transport(), 0.0, random.Random(0))
    assert {await _status_of(transport) for _ in range(20)} == {200}


async def test_rate_one_fails_every_request() -> None:
    transport = FaultyTransport(_ok_transport(), 1.0, random.Random(0))
    assert {await _status_of(transport) for _ in range(20)} == {UNHEALTHY_STATUS}


def test_rate_outside_unit_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="fault rate"):
        FaultyTransport(_ok_transport(), 1.5, random.Random(0))


class _FakeFirecrest:
    """The two attributes of AsyncFirecrest that install_faults relies on."""

    def __init__(self) -> None:
        self._session = httpx.AsyncClient(transport=_ok_transport(), base_url="https://f7t.test")

    async def create_new_session(self) -> None:
        self._session = httpx.AsyncClient(transport=_ok_transport(), base_url="https://f7t.test")


async def test_faults_survive_a_new_session() -> None:
    client = _FakeFirecrest()
    install_faults(client, rate=1.0, seed=0)
    assert (await client._session.get("/a")).status_code == UNHEALTHY_STATUS

    await client.create_new_session()

    assert (await client._session.get("/b")).status_code == UNHEALTHY_STATUS
