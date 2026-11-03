from pathlib import Path

import pytest

from multicluster.arch import Arch
from multicluster.jobs import ClusterJobs, QualifiedJobId, parse_state
from multicluster.spec import JobSpec, JobVariant, NoVariantError
from tests.fakes import FakeFirecrest, profile

SCRIPT = Path(__file__).resolve().parent.parent / "jobs" / "probe.sbatch"
SPEC = JobSpec(
    name="probe",
    script=SCRIPT,
    stdout="mc-probe-{job_id}.out",
    variants={Arch.NVIDIA: JobVariant(env={"IMAGE_ARCH": "nvidia"})},
)


def test_qualified_ids_round_trip() -> None:
    job = QualifiedJobId.parse("mock-amd:12345")
    assert job == QualifiedJobId("mock-amd", "12345")
    assert str(job) == "mock-amd:12345"


@pytest.mark.parametrize("text", ["12345", "mock-amd:", ":12", "mock-amd:abc"])
def test_unqualified_or_malformed_ids_are_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="<cluster>:<job id>"):
        QualifiedJobId.parse(text)


def test_state_of_a_job_not_listed_yet_is_pending() -> None:
    assert parse_state([]) == "PENDING"


def test_state_detail_is_dropped() -> None:
    assert parse_state([{"status": {"state": "CANCELLED by 42"}}]) == "CANCELLED"


async def test_submit_sends_the_clusters_variant_and_settings() -> None:
    client = FakeFirecrest()
    nv = profile("mock-nv", Arch.NVIDIA, partition="normal", account="hack01", mock=True)
    job = await ClusterJobs(nv, client).submit(SPEC)

    assert job.cluster == "mock-nv"
    (sent,) = client.submitted
    assert sent["env_vars"] == {"IMAGE_ARCH": "nvidia", "MOCK_CLUSTER_ARCH": "nvidia"}
    assert (sent["system_name"], sent["partition"], sent["account"]) == ("daint", "normal", "hack01")
    assert sent["script_str"] == SCRIPT.read_text()


async def test_submit_refuses_a_cluster_the_job_has_no_variant_for() -> None:
    client = FakeFirecrest()
    with pytest.raises(NoVariantError):
        await ClusterJobs(profile("mock-amd", Arch.AMD), client).submit(SPEC)
    assert client.submitted == []


async def test_wait_polls_until_a_terminal_state_then_reads_output() -> None:
    nv = profile("mock-nv", Arch.NVIDIA)
    jobs = ClusterJobs(nv, FakeFirecrest(polls_until_done=3), poll_sec=0)
    job = await jobs.submit(SPEC)

    assert await jobs.wait(job) == "COMPLETED"
    assert f"/scratch/mc-probe-{job.job_id}.out" in await jobs.output(SPEC, job)
