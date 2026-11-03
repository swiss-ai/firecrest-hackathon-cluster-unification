"""Pick clusters by name or architecture and check that their instances answer.

The routing lives inside the tool: given the registry, the caller names a
cluster (or just the architecture it needs) and the router supplies the
matching profile and its client. Instances are queried concurrently and
independently, so one that is down only takes itself out.
"""

import asyncio
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from multicluster.arch import Arch
from multicluster.clients import ClientPool
from multicluster.errors import describe_error
from multicluster.profiles import ClusterProfile
from multicluster.retry import with_retry

DEFAULT_TIMEOUT_SEC = 60.0


class RoutingError(LookupError):
    """No cluster in the registry matches the request."""


@dataclass(frozen=True)
class Health:
    cluster: str
    up: bool
    detail: str
    latency_sec: float


class ClusterRouter:
    def __init__(
        self,
        profiles: Mapping[str, ClusterProfile],
        pool: ClientPool,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        self._profiles = dict(profiles)
        self._pool = pool
        self.timeout_sec = timeout_sec

    @property
    def names(self) -> list[str]:
        return list(self._profiles)

    def select(self, names: Sequence[str] | None = None, arch: Arch | None = None) -> list[ClusterProfile]:
        """The clusters named (default: all), narrowed to ``arch`` if given."""
        unknown = [name for name in names or () if name not in self._profiles]
        if unknown:
            raise RoutingError(f"unknown cluster(s) {', '.join(unknown)}; known: {', '.join(self.names)}")
        chosen = [self._profiles[name] for name in names] if names else list(self._profiles.values())
        if arch is not None:
            chosen = [profile for profile in chosen if profile.arch == arch]
        if not chosen:
            raise RoutingError(f"no {arch} cluster among {', '.join(names or self.names)}")
        return chosen

    def client(self, profile: ClusterProfile) -> Any:
        return self._pool.get(profile)

    async def aclose(self) -> None:
        await self._pool.aclose()

    async def health(self, profiles: Iterable[ClusterProfile]) -> list[Health]:
        return list(await asyncio.gather(*(self._check(profile) for profile in profiles)))

    async def _check(self, profile: ClusterProfile) -> Health:
        started = time.monotonic()
        try:
            client = self.client(profile)
            systems = await asyncio.wait_for(with_retry(client.systems), self.timeout_sec)
        except Exception as exc:
            return Health(profile.name, False, describe_error(exc), time.monotonic() - started)
        latency = time.monotonic() - started
        listed = [str(system.get("name")) for system in systems]
        if profile.system not in listed:
            detail = f"instance does not serve system {profile.system!r} (it serves: {', '.join(listed)})"
            return Health(profile.name, False, detail, latency)
        return Health(profile.name, True, f"{profile.system} via {profile.firecrest_url}", latency)
