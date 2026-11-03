"""An in-memory stand-in for pyfirecrest's AsyncFirecrest, for tests without network."""

import itertools
from collections.abc import Callable
from typing import Any

import firecrest as f7t
import httpx

from multicluster.arch import Arch
from multicluster.profiles import ClusterProfile


def status_error(status: int) -> f7t.UnexpectedStatusException:
    return f7t.UnexpectedStatusException([httpx.Response(status)], expected_status_code=200)


def profile(name: str, arch: Arch, system: str = "daint", **extra: Any) -> ClusterProfile:
    return ClusterProfile(
        name=name,
        arch=arch,
        firecrest_url=f"https://{name}.test/v2",
        client_id_env=f"{name}_ID",
        client_secret_env=f"{name}_SECRET",
        system=system,
        working_dir="/scratch",
        **extra,
    )


class FakeFirecrest:
    """Jobs finish in ``final_state`` after ``polls_until_done`` status queries."""

    _ids = itertools.count(1000)

    def __init__(
        self,
        systems: list[str] | None = None,
        final_state: str = "COMPLETED",
        polls_until_done: int = 1,
        fail_with: Callable[[], Exception] | None = None,
    ) -> None:
        self._systems = systems or ["daint"]
        self._final_state = final_state
        self._polls_until_done = polls_until_done
        self._fail_with = fail_with
        self.submitted: list[dict[str, Any]] = []
        self.systems_calls = 0
        self.cancelled: list[str] = []
        self._polls: dict[str, int] = {}

    def _maybe_fail(self) -> None:
        if self._fail_with is not None:
            raise self._fail_with()

    async def systems(self) -> list[dict[str, Any]]:
        self.systems_calls += 1
        self._maybe_fail()
        return [{"name": name} for name in self._systems]

    async def submit(self, **kwargs: Any) -> dict[str, Any]:
        self._maybe_fail()
        self.submitted.append(kwargs)
        return {"jobId": next(self._ids)}

    async def job_info(self, system_name: str, jobid: str, **_: Any) -> list[dict[str, Any]]:
        self._maybe_fail()
        self._polls[jobid] = self._polls.get(jobid, 0) + 1
        done = self._polls[jobid] >= self._polls_until_done
        return [{"jobId": int(jobid), "status": {"state": self._final_state if done else "RUNNING"}}]

    async def view(self, system_name: str, path: str) -> str:
        self._maybe_fail()
        return f"MC_RESULT path={path}\nMC_OK\n"

    async def cancel_job(self, system_name: str, jobid: str) -> dict[str, Any]:
        self.cancelled.append(jobid)
        return {}

    async def close_session(self) -> None:
        return None
