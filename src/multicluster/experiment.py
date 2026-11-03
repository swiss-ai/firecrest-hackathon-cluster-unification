"""Run one job on several clusters at once and report per cluster.

Each cluster goes through the same steps (architecture check, health check,
submit, wait, read output) independently; whatever happens on one cluster is
recorded in its result and never stops the others.
"""

import asyncio
import time
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from multicluster.errors import describe_error
from multicluster.jobs import DEFAULT_POLL_SEC, ClusterJobs, QualifiedJobId
from multicluster.profiles import ClusterProfile
from multicluster.router import ClusterRouter
from multicluster.spec import JobSpec, NoVariantError


class Outcome(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"  # the job ran and did not complete
    REJECTED = "rejected"  # the job has no variant for this cluster's architecture
    UNREACHABLE = "unreachable"  # the instance could not be used

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ClusterResult:
    cluster: str
    outcome: Outcome
    detail: str
    wall_sec: float
    job: QualifiedJobId | None = None
    output: str = ""


async def run_on_clusters(
    router: ClusterRouter,
    spec: JobSpec,
    profiles: Iterable[ClusterProfile],
    poll_sec: float = DEFAULT_POLL_SEC,
) -> list[ClusterResult]:
    runs = (_run_on_cluster(router, spec, profile, poll_sec) for profile in profiles)
    return list(await asyncio.gather(*runs))


async def _run_on_cluster(
    router: ClusterRouter, spec: JobSpec, profile: ClusterProfile, poll_sec: float
) -> ClusterResult:
    started = time.monotonic()

    def result(
        outcome: Outcome, detail: str, job: QualifiedJobId | None = None, output: str = ""
    ) -> ClusterResult:
        wall_sec = round(time.monotonic() - started, 1)
        return ClusterResult(profile.name, outcome, detail, wall_sec, job, output)

    try:
        spec.variant_for(profile.arch)
    except NoVariantError as exc:
        return result(Outcome.REJECTED, str(exc))

    (health,) = await router.health([profile])
    if not health.up:
        return result(Outcome.UNREACHABLE, health.detail)

    jobs = ClusterJobs(profile, router.client(profile), poll_sec)
    try:
        job = await jobs.submit(spec)
    except Exception as exc:
        return result(Outcome.UNREACHABLE, f"submit failed: {describe_error(exc)}")

    try:
        state = await jobs.wait(job)
        output = await jobs.output(spec, job)
    except Exception as exc:
        return result(Outcome.UNREACHABLE, f"lost track of the job: {describe_error(exc)}", job=job)

    outcome = Outcome.COMPLETED if state == "COMPLETED" else Outcome.FAILED
    return result(outcome, state, job=job, output=output.strip())
