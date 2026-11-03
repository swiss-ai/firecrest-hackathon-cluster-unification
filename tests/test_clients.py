from collections.abc import Mapping
from typing import Any

import pytest

from multicluster.arch import Arch
from multicluster.clients import ClientPool, build_client
from multicluster.profiles import ClusterProfile, ProfileError


def _profile(name: str = "mock-amd") -> ClusterProfile:
    return ClusterProfile(
        name=name,
        arch=Arch.AMD,
        firecrest_url="https://f7t.test/v2",
        client_id_env="ID",
        client_secret_env="SECRET",
        system="daint",
        working_dir="/scratch",
    )


class _Closable:
    closed = False

    async def close_session(self) -> None:
        self.closed = True


def test_a_cluster_gets_one_client_reused_across_calls() -> None:
    built: list[str] = []

    def factory(profile: ClusterProfile, env: Mapping[str, str]) -> Any:
        built.append(profile.name)
        return _Closable()

    pool = ClientPool(env={}, factory=factory)
    first = pool.get(_profile())
    assert pool.get(_profile()) is first
    pool.get(_profile("mock-nv"))
    assert built == ["mock-amd", "mock-nv"]


async def test_closing_the_pool_closes_every_client() -> None:
    pool = ClientPool(env={}, factory=lambda profile, env: _Closable())
    client = pool.get(_profile())
    await pool.aclose()
    assert client.closed


def test_build_client_points_at_the_profiles_instance() -> None:
    client = build_client(_profile(), {"ID": "abc", "SECRET": "xyz"})
    assert client._firecrest_url == "https://f7t.test/v2"


def test_build_client_without_credentials_names_the_variables() -> None:
    with pytest.raises(ProfileError, match="set ID and SECRET"):
        build_client(_profile(), {})
