from collections.abc import Mapping
from typing import Any

import pytest

from multicluster.arch import Arch
from multicluster.clients import ClientPool
from multicluster.profiles import ClusterProfile
from multicluster.router import ClusterRouter, RoutingError
from tests.fakes import FakeFirecrest, profile, status_error

NV = profile("mock-nv", Arch.NVIDIA)
AMD = profile("mock-amd", Arch.AMD)


def _router(clients: Mapping[str, Any]) -> ClusterRouter:
    def factory(p: ClusterProfile, env: Mapping[str, str]) -> Any:
        return clients[p.name]

    return ClusterRouter({p.name: p for p in (NV, AMD)}, ClientPool(env={}, factory=factory), timeout_sec=5)


def test_select_defaults_to_every_cluster() -> None:
    assert [p.name for p in _router({}).select()] == ["mock-nv", "mock-amd"]


def test_select_by_arch_routes_to_matching_clusters_only() -> None:
    assert [p.name for p in _router({}).select(arch=Arch.AMD)] == ["mock-amd"]


def test_select_rejects_unknown_names_and_lists_known_ones() -> None:
    with pytest.raises(RoutingError, match=r"unknown cluster.*beverin; known: mock-nv, mock-amd"):
        _router({}).select(["beverin"])


def test_select_with_no_arch_match_is_an_error() -> None:
    with pytest.raises(RoutingError, match="no amd cluster among mock-nv"):
        _router({}).select(["mock-nv"], arch=Arch.AMD)


async def test_one_unhealthy_instance_does_not_affect_the_other() -> None:
    unauthorized = FakeFirecrest(fail_with=lambda: status_error(401))
    router = _router({"mock-nv": FakeFirecrest(), "mock-amd": unauthorized})
    nv, amd = await router.health(router.select())
    assert nv.up
    assert not amd.up
    assert "OIDC client" in amd.detail


async def test_instance_that_does_not_serve_the_system_is_down() -> None:
    router = _router({"mock-nv": FakeFirecrest(systems=["clariden"]), "mock-amd": FakeFirecrest()})
    (nv,) = await router.health(router.select(["mock-nv"]))
    assert not nv.up
    assert "does not serve system 'daint' (it serves: clariden)" in nv.detail
