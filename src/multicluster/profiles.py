"""The cluster registry: everything needed to reach one cluster, under one name.

Today a cluster's FirecREST URL, OIDC client, system name, partition and
architecture are separate settings that each tool keeps in its own way. A
profile keeps them together, so callers say *which* cluster and never *how*.
Secrets stay in the environment; a profile only names the variables.
"""

import re
import sys
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from multicluster.arch import Arch

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

DEFAULT_TOKEN_URI = "https://auth.cscs.ch/auth/realms/firecrest-clients/protocol/openid-connect/token"  # noqa: S105 - a public endpoint, not a secret

_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ProfileError(ValueError):
    """A cluster profile is incomplete or refers to unset environment variables."""


class Credentials(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_id: str
    client_secret: str


class ClusterProfile(BaseModel):
    """One cluster as reached through its FirecREST instance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    arch: Arch
    firecrest_url: str
    token_uri: str = DEFAULT_TOKEN_URI
    client_id_env: str = Field(description="Environment variable holding the OIDC client ID.")
    client_secret_env: str = Field(description="Environment variable holding the OIDC client secret.")
    system: str = Field(description="System name as this FirecREST instance lists it.")
    working_dir: str
    partition: str | None = None
    account: str | None = None
    mock: bool = Field(default=False, description="Tell jobs which arch this cluster pretends to be.")
    fault_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Share of requests answered 503.")

    def credentials(self, env: Mapping[str, str]) -> Credentials:
        missing = [name for name in (self.client_id_env, self.client_secret_env) if not env.get(name)]
        if missing:
            raise ProfileError(f"cluster {self.name!r}: set {' and '.join(missing)}")
        return Credentials(client_id=env[self.client_id_env], client_secret=env[self.client_secret_env])


def _expand(value: object, env: Mapping[str, str], where: str) -> object:
    """Replace ``${VAR}`` in strings; an unset variable is an error, not an empty string."""
    if not isinstance(value, str):
        return value

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in env:
            raise ProfileError(f"{where}: environment variable {name} is not set")
        return env[name]

    return _ENV_REFERENCE.sub(substitute, value)


def parse_profiles(data: Mapping[str, object], env: Mapping[str, str]) -> dict[str, ClusterProfile]:
    clusters = data.get("clusters")
    if not isinstance(clusters, dict) or not clusters:
        raise ProfileError("no [clusters.<name>] tables found")
    profiles: dict[str, ClusterProfile] = {}
    for name, table in clusters.items():
        if not isinstance(table, dict):
            raise ProfileError(f"[clusters.{name}] must be a table")
        fields = {key: _expand(value, env, f"clusters.{name}.{key}") for key, value in table.items()}
        profiles[name] = ClusterProfile.model_validate({"name": name, **fields})
    return profiles


def load_profiles(path: Path, env: Mapping[str, str]) -> dict[str, ClusterProfile]:
    with path.open("rb") as file:
        return parse_profiles(tomllib.load(file), env)
