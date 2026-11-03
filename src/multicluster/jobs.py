"""Submit, follow and read jobs on one cluster.

Job IDs are only unique within a cluster, so outside this module a job is
always a ``QualifiedJobId`` like ``mock-amd:12345``.
"""

import asyncio
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from multicluster.profiles import ClusterProfile
from multicluster.retry import with_retry
from multicluster.spec import JobSpec

DEFAULT_POLL_SEC = 5.0
TERMINAL_STATES = frozenset(
    {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "PREEMPTED", "BOOT_FAIL"}
)
MOCK_ARCH_VARIABLE = "MOCK_CLUSTER_ARCH"


@dataclass(frozen=True)
class QualifiedJobId:
    cluster: str
    job_id: str

    def __str__(self) -> str:
        return f"{self.cluster}:{self.job_id}"

    @classmethod
    def parse(cls, text: str) -> "QualifiedJobId":
        cluster, sep, job_id = text.rpartition(":")
        if not sep or not cluster or not job_id.isdigit():
            raise ValueError(f"expected <cluster>:<job id>, got {text!r}")
        return cls(cluster, job_id)


class WaitTimeout(TimeoutError):
    """A job did not reach a terminal state in time."""

    def __init__(self, job: "QualifiedJobId", waited_sec: float, last_state: str) -> None:
        super().__init__(f"{job} still {last_state} after {waited_sec:.0f} s")
        self.last_state = last_state


def parse_state(jobs: list[dict[str, Any]]) -> str:
    """The Slurm state of a ``job_info`` answer; a job not listed yet is pending."""
    if not jobs:
        return "PENDING"
    # Slurm may append detail, e.g. "CANCELLED by 12345".
    return str(jobs[0]["status"]["state"]).split()[0]


class ClusterJobs:
    def __init__(self, profile: ClusterProfile, client: Any, poll_sec: float = DEFAULT_POLL_SEC) -> None:
        self._profile = profile
        self._client = client
        self._poll_sec = poll_sec

    def _job_env(self, spec: JobSpec) -> dict[str, str]:
        env = dict(spec.variant_for(self._profile.arch).env)
        if self._profile.mock:
            env[MOCK_ARCH_VARIABLE] = str(self._profile.arch)
        return env

    async def submit(self, spec: JobSpec) -> QualifiedJobId:
        """Submit ``spec``'s variant for this cluster's architecture.

        Not retried: FirecREST may report an error for an sbatch that went through.
        """
        env = self._job_env(spec)
        report = await self._client.submit(
            system_name=self._profile.system,
            working_dir=self._profile.working_dir,
            script_str=spec.script.read_text(),
            env_vars=env,
            account=self._profile.account,
            partition=self._profile.partition,
            reservation=self._profile.reservation,
        )
        return QualifiedJobId(self._profile.name, str(report["jobId"]))

    async def state(self, job: QualifiedJobId) -> str:
        system = self._profile.system
        jobs = await with_retry(lambda: self._client.job_info(system_name=system, jobid=job.job_id))
        return parse_state(jobs)

    async def wait(self, job: QualifiedJobId, max_wait_sec: float | None = None) -> str:
        """Poll until the job ends; with ``max_wait_sec``, raise ``WaitTimeout`` past it."""
        started = time.monotonic()
        while (state := await self.state(job)) not in TERMINAL_STATES:
            waited = time.monotonic() - started
            if max_wait_sec is not None and waited >= max_wait_sec:
                raise WaitTimeout(job, waited, state)
            await asyncio.sleep(self._poll_sec)
        return state

    async def output(self, spec: JobSpec, job: QualifiedJobId) -> str:
        path = str(PurePosixPath(self._profile.working_dir) / spec.stdout_name(job.job_id))
        text: str = await with_retry(lambda: self._client.view(system_name=self._profile.system, path=path))
        return text

    async def cancel(self, job: QualifiedJobId) -> None:
        await with_retry(lambda: self._client.cancel_job(system_name=self._profile.system, jobid=job.job_id))
