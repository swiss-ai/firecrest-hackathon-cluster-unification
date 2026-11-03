from pathlib import Path

import pytest

from multicluster.arch import Arch
from multicluster.spec import JobSpec, JobVariant, NoVariantError, load_job_spec

JOBS_DIR = Path(__file__).resolve().parent.parent / "jobs"


def _cuda_only() -> JobSpec:
    return JobSpec(
        name="bench",
        script=Path("bench.sbatch"),
        stdout="bench-{job_id}.out",
        variants={Arch.NVIDIA: JobVariant(env={"IMAGE_ARCH": "nvidia"})},
    )


def test_variant_for_an_available_arch() -> None:
    assert _cuda_only().variant_for(Arch.NVIDIA).env == {"IMAGE_ARCH": "nvidia"}


def test_missing_variant_names_the_arch_and_what_exists() -> None:
    with pytest.raises(NoVariantError, match=r"no amd variant \(available: nvidia\)"):
        _cuda_only().variant_for(Arch.AMD)


def test_stdout_name_fills_in_the_job_id() -> None:
    assert _cuda_only().stdout_name("42") == "bench-42.out"


def test_shipped_probe_specs_load_with_scripts_next_to_them() -> None:
    probe = load_job_spec(JOBS_DIR / "probe.toml")
    assert set(probe.variants) == {Arch.NVIDIA, Arch.AMD}
    assert probe.script == JOBS_DIR / "probe.sbatch"

    cuda_only = load_job_spec(JOBS_DIR / "probe-cuda-only.toml")
    assert set(cuda_only.variants) == {Arch.NVIDIA}
