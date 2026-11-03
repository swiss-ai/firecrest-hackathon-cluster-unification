from collections.abc import Mapping
from pathlib import Path
from typing import Any

from multicluster.arch import Arch
from multicluster.clients import ClientPool
from multicluster.experiment import Outcome, run_on_clusters
from multicluster.profiles import ClusterProfile
from multicluster.router import ClusterRouter
from multicluster.spec import JobSpec, JobVariant
from tests.fakes import FakeFirecrest, profile, status_error

SCRIPT = Path(__file__).resolve().parent.parent / "jobs" / "probe.sbatch"
NV = profile("mock-nv", Arch.NVIDIA)
AMD = profile("mock-amd", Arch.AMD)


def _spec(*arches: Arch) -> JobSpec:
    return JobSpec(
        name="probe",
        script=SCRIPT,
        stdout="mc-probe-{job_id}.out",
        variants={arch: JobVariant(env={"IMAGE_ARCH": str(arch)}) for arch in arches},
    )


def _router(clients: Mapping[str, Any]) -> ClusterRouter:
    def factory(p: ClusterProfile, env: Mapping[str, str]) -> Any:
        return clients[p.name]

    return ClusterRouter({p.name: p for p in (NV, AMD)}, ClientPool(env={}, factory=factory), timeout_sec=5)


async def test_runs_on_every_cluster_with_its_own_variant() -> None:
    nv, amd = FakeFirecrest(), FakeFirecrest()
    router = _router({"mock-nv": nv, "mock-amd": amd})

    results = await run_on_clusters(router, _spec(Arch.NVIDIA, Arch.AMD), router.select(), poll_sec=0)

    assert [(r.cluster, r.outcome) for r in results] == [
        ("mock-nv", Outcome.COMPLETED),
        ("mock-amd", Outcome.COMPLETED),
    ]
    assert nv.submitted[0]["env_vars"]["IMAGE_ARCH"] == "nvidia"
    assert amd.submitted[0]["env_vars"]["IMAGE_ARCH"] == "amd"
    assert all(r.job is not None and r.job.cluster == r.cluster for r in results)


async def test_cluster_without_a_variant_is_rejected_before_submission() -> None:
    amd = FakeFirecrest()
    router = _router({"mock-nv": FakeFirecrest(), "mock-amd": amd})

    _, amd_result = await run_on_clusters(router, _spec(Arch.NVIDIA), router.select(), poll_sec=0)

    assert amd_result.outcome is Outcome.REJECTED
    assert amd.submitted == []


async def test_unhealthy_cluster_is_reported_and_the_other_still_completes() -> None:
    forbidden = FakeFirecrest(fail_with=lambda: status_error(403))
    router = _router({"mock-nv": FakeFirecrest(), "mock-amd": forbidden})
    spec = _spec(Arch.NVIDIA, Arch.AMD)

    nv_result, amd_result = await run_on_clusters(router, spec, router.select(), poll_sec=0)

    assert nv_result.outcome is Outcome.COMPLETED
    assert amd_result.outcome is Outcome.UNREACHABLE
    assert "forbidden" in amd_result.detail


async def test_a_job_that_ends_badly_is_failed_with_its_state() -> None:
    router = _router({"mock-nv": FakeFirecrest(final_state="TIMEOUT"), "mock-amd": FakeFirecrest()})

    (result,) = await run_on_clusters(router, _spec(Arch.NVIDIA), router.select(["mock-nv"]), poll_sec=0)

    assert (result.outcome, result.detail) == (Outcome.FAILED, "TIMEOUT")
