"""One FirecREST client per cluster, built on first use and reused afterwards."""

import os
from collections.abc import Callable, Mapping
from typing import Any

import firecrest as f7t

from multicluster.faults import install_faults
from multicluster.profiles import ClusterProfile

# FirecREST rejects a token with < 30 s left by its clock; pyfirecrest measures the
# remaining life by ours. Same margin as sml, to survive clock skew.
MIN_TOKEN_VALIDITY_SEC = 180

ClientFactory = Callable[[ClusterProfile, Mapping[str, str]], Any]


def build_client(profile: ClusterProfile, env: Mapping[str, str]) -> f7t.v2.AsyncFirecrest:
    """A client for ``profile``'s instance, authenticated with its own OIDC client."""
    credentials = profile.credentials(env)
    client = f7t.v2.AsyncFirecrest(
        firecrest_url=profile.firecrest_url,
        authorization=f7t.ClientCredentialsAuth(
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
            token_uri=profile.token_uri,
            min_token_validity=MIN_TOKEN_VALIDITY_SEC,
        ),
    )
    install_faults(client, profile.fault_rate)
    return client


class ClientPool:
    """Hands out each cluster's client, creating it lazily.

    Lazy creation matters: a cluster whose credentials are missing only fails
    when it is used, so it cannot block work on the others.
    """

    def __init__(
        self,
        env: Mapping[str, str] | None = None,
        factory: ClientFactory = build_client,
    ) -> None:
        self._env = os.environ if env is None else env
        self._factory = factory
        self._clients: dict[str, Any] = {}

    def get(self, profile: ClusterProfile) -> Any:
        if profile.name not in self._clients:
            self._clients[profile.name] = self._factory(profile, self._env)
        return self._clients[profile.name]

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.close_session()
        self._clients.clear()
