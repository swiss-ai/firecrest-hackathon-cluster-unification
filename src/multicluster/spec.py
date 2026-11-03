"""What to run, with one software variant per architecture.

A job built for CUDA cannot run on an AMD node, and today nothing notices until
the job starts. A ``JobSpec`` lists the variants it has; asking for an
architecture it lacks fails before anything is submitted.
"""

import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from multicluster.arch import Arch

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


class NoVariantError(LookupError):
    """The job has no software variant for a cluster's architecture."""

    def __init__(self, job: str, arch: Arch, available: list[Arch]) -> None:
        names = ", ".join(sorted(str(a) for a in available)) or "none"
        super().__init__(f"job {job!r} has no {arch} variant (available: {names})")
        self.arch = arch


class JobVariant(BaseModel):
    """The architecture-specific part of a job, passed to it as environment variables."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    env: dict[str, str] = Field(default_factory=dict)


class JobSpec(BaseModel):
    """A batch script plus the variants it can run as."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    script: Path
    stdout: str = Field(description="Output file name, relative to the working dir; {job_id} is filled in.")
    variants: dict[Arch, JobVariant]

    def variant_for(self, arch: Arch) -> JobVariant:
        try:
            return self.variants[arch]
        except KeyError:
            raise NoVariantError(self.name, arch, list(self.variants)) from None

    def stdout_name(self, job_id: str) -> str:
        return self.stdout.format(job_id=job_id)


def load_job_spec(path: Path) -> JobSpec:
    """Read a job spec TOML; its ``script`` is resolved relative to the TOML file."""
    with path.open("rb") as file:
        data = tomllib.load(file)
    spec = JobSpec.model_validate(data)
    return spec.model_copy(update={"script": (path.parent / spec.script).resolve()})
