import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from multicluster import cli
from multicluster.clients import ClientPool
from multicluster.profiles import ClusterProfile
from tests.fakes import FakeFirecrest, status_error

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = str(ROOT / "clusters.example.toml")
PROBE = str(ROOT / "jobs" / "probe.toml")
CUDA_ONLY = str(ROOT / "jobs" / "probe-cuda-only.toml")


@pytest.fixture
def fake_clusters(monkeypatch: pytest.MonkeyPatch) -> dict[str, FakeFirecrest]:
    monkeypatch.setenv("HACKATHON_ACCOUNT", "hack01")
    monkeypatch.setenv("HACKATHON_SCRATCH", "/scratch")
    clients = {"mock-nv": FakeFirecrest(), "mock-amd": FakeFirecrest()}

    def factory(profile: ClusterProfile, env: Mapping[str, str]) -> Any:
        return clients[profile.name]

    monkeypatch.setattr(cli, "ClientPool", lambda: ClientPool(env={}, factory=factory))
    return clients


def _run_json(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, list[dict[str, Any]]]:
    code = cli.main(["--config", EXAMPLE, "run", *args, "--poll", "0", "--json"])
    return code, json.loads(capsys.readouterr().out)


def test_run_on_every_cluster(
    fake_clusters: dict[str, FakeFirecrest], capsys: pytest.CaptureFixture[str]
) -> None:
    code, results = _run_json(capsys, PROBE)
    assert code == 0
    assert [(r["cluster"], r["outcome"]) for r in results] == [
        ("mock-nv", "completed"),
        ("mock-amd", "completed"),
    ]
    assert all(r["job"].startswith(r["cluster"] + ":") for r in results)


def test_run_by_arch_only_touches_matching_clusters(
    fake_clusters: dict[str, FakeFirecrest], capsys: pytest.CaptureFixture[str]
) -> None:
    code, results = _run_json(capsys, PROBE, "--arch", "amd")
    assert code == 0
    assert [r["cluster"] for r in results] == ["mock-amd"]
    assert fake_clusters["mock-nv"].submitted == []


def test_cuda_only_job_is_rejected_on_the_amd_cluster(
    fake_clusters: dict[str, FakeFirecrest], capsys: pytest.CaptureFixture[str]
) -> None:
    code, results = _run_json(capsys, CUDA_ONLY)
    assert code == 1
    assert {r["cluster"]: r["outcome"] for r in results} == {"mock-nv": "completed", "mock-amd": "rejected"}


def test_doctor_reports_a_down_cluster(
    fake_clusters: dict[str, FakeFirecrest], capsys: pytest.CaptureFixture[str]
) -> None:
    fake_clusters["mock-amd"] = FakeFirecrest(fail_with=lambda: status_error(401))
    assert cli.main(["--config", EXAMPLE, "doctor"]) == 1
    out = capsys.readouterr().out
    assert "up   mock-nv" in out
    assert "DOWN mock-amd" in out


def test_unset_config_variable_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("HACKATHON_ACCOUNT", raising=False)
    assert cli.main(["--config", EXAMPLE, "doctor"]) == 2
    assert "HACKATHON_ACCOUNT is not set" in capsys.readouterr().err


def test_status_needs_a_qualified_job_id(
    fake_clusters: dict[str, FakeFirecrest], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--config", EXAMPLE, "status", "12345"]) == 2
    assert "<cluster>:<job id>" in capsys.readouterr().err


def test_fault_flag_must_name_a_known_cluster(
    fake_clusters: dict[str, FakeFirecrest], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--config", EXAMPLE, "--fault", "beverin=0.5", "doctor"]) == 2
    assert "unknown cluster 'beverin'" in capsys.readouterr().err
