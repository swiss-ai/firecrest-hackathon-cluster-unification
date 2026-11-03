from pathlib import Path

import pytest

from multicluster.arch import Arch
from multicluster.profiles import DEFAULT_TOKEN_URI, ProfileError, load_profiles, parse_profiles

EXAMPLE = Path(__file__).resolve().parent.parent / "clusters.example.toml"
ENV = {
    "HACKATHON_ACCOUNT": "hack01",
    "HACKATHON_SCRATCH": "/capstor/scratch/cscs/me",
    "CLARIDEN_ACCOUNT": "infra01",
    "CLARIDEN_SCRATCH": "/capstor/scratch/cscs/me",
}


def _table(**overrides: object) -> dict[str, object]:
    table: dict[str, object] = {
        "arch": "amd",
        "firecrest_url": "https://f7t.test/v2",
        "client_id_env": "ID",
        "client_secret_env": "SECRET",
        "system": "beverin",
        "working_dir": "/scratch",
    }
    return {**table, **overrides}


def test_example_config_defines_the_mock_clusters_and_clariden() -> None:
    profiles = load_profiles(EXAMPLE, ENV)
    assert {name: p.arch for name, p in profiles.items()} == {
        "mock-nv": Arch.NVIDIA,
        "mock-amd": Arch.AMD,
        "clariden": Arch.NVIDIA,
    }
    assert profiles["clariden"].firecrest_url != profiles["mock-nv"].firecrest_url
    assert profiles["mock-amd"].account == "hack01"
    assert profiles["mock-amd"].working_dir == "/capstor/scratch/cscs/me"
    assert profiles["mock-amd"].token_uri == DEFAULT_TOKEN_URI


def test_unset_variable_is_an_error_naming_the_field() -> None:
    data = {"clusters": {"b": _table(working_dir="${NOPE}")}}
    with pytest.raises(ProfileError, match=r"clusters\.b\.working_dir: environment variable NOPE"):
        parse_profiles(data, {})


def test_credentials_come_from_the_named_variables() -> None:
    profile = parse_profiles({"clusters": {"b": _table()}}, {})["b"]
    creds = profile.credentials({"ID": "abc", "SECRET": "xyz"})
    assert (creds.client_id, creds.client_secret) == ("abc", "xyz")


def test_missing_credentials_name_every_unset_variable() -> None:
    profile = parse_profiles({"clusters": {"b": _table()}}, {})["b"]
    with pytest.raises(ProfileError, match="cluster 'b': set ID and SECRET"):
        profile.credentials({})


@pytest.mark.parametrize(
    "data",
    [{}, {"clusters": {}}, {"clusters": {"b": "not a table"}}],
)
def test_malformed_configs_are_rejected(data: dict[str, object]) -> None:
    with pytest.raises(ProfileError):
        parse_profiles(data, {})


def test_fault_rate_must_be_a_share() -> None:
    with pytest.raises(ValueError, match="fault_rate"):
        parse_profiles({"clusters": {"b": _table(fault_rate=2)}}, {})
