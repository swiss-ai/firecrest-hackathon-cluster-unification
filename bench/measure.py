"""Run each scenario through the baseline and through ``mc``; record what happened.

    uv run python bench/measure.py                 # every scenario
    uv run python bench/measure.py happy outage    # some of them

Needs the same environment as the tools (MOCK_*_CLIENT_ID/SECRET,
HACKATHON_ACCOUNT, HACKATHON_SCRATCH) and a clusters.toml. Writes one JSON file
per invocation to results/raw/ and prints a Markdown table for docs/02-results.md.
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results" / "raw"


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    baseline_env: dict[str, str] = field(default_factory=dict)
    mc_job: str = "jobs/probe.toml"
    amd_fault_rate: float = 0.0  # share of the AMD instance's requests answered 503, in both tools


SCENARIOS = [
    Scenario("happy", "both clusters healthy, right variant on each"),
    Scenario(
        "wrong-variant",
        "a CUDA-only job sent to the AMD cluster",
        baseline_env={"IMAGE_ARCH_MOCK_AMD": "nvidia"},
        mc_job="jobs/probe-cuda-only.toml",
    ),
    Scenario("flaky", "AMD instance answers 30% of requests with 503", amd_fault_rate=0.3),
    Scenario("outage", "AMD instance down (every request 503)", amd_fault_rate=1.0),
]


@dataclass(frozen=True)
class Measurement:
    scenario: str
    tool: str
    exit_code: int
    wall_sec: float
    stdout: str
    stderr_tail: str


def _measure(scenario: Scenario, tool: str, command: list[str], extra_env: dict[str, str]) -> Measurement:
    started = time.monotonic()
    done = subprocess.run(  # noqa: S603 - fixed commands from this file
        command, cwd=ROOT, env={**os.environ, **extra_env}, capture_output=True, text=True, check=False
    )
    return Measurement(
        scenario=scenario.name,
        tool=tool,
        exit_code=done.returncode,
        wall_sec=round(time.monotonic() - started, 1),
        stdout=done.stdout.strip(),
        stderr_tail="\n".join(done.stderr.strip().splitlines()[-5:]),
    )


def _run_scenario(scenario: Scenario) -> list[Measurement]:
    baseline_env = {**scenario.baseline_env, "MOCK_AMD_FAULT_RATE": str(scenario.amd_fault_rate)}
    baseline = _measure(scenario, "baseline", ["bash", "baseline/run_all.sh"], baseline_env)
    # The baseline only knows the two mock clusters, so mc runs on the same two.
    fault = ["--fault", f"mock-amd={scenario.amd_fault_rate}"]
    mc_command = [
        "uv",
        "run",
        "mc",
        *fault,
        "run",
        scenario.mc_job,
        "--clusters",
        "mock-nv,mock-amd",
        "--json",
    ]
    unified = _measure(scenario, "mc", mc_command, {})
    return [baseline, unified]


def _table(measurements: list[Measurement]) -> str:
    rows = ["| scenario | tool | exit | wall (s) |", "|---|---|---|---|"]
    rows += [f"| {m.scenario} | {m.tool} | {m.exit_code} | {m.wall_sec} |" for m in measurements]
    return "\n".join(rows)


def main(names: list[str]) -> int:
    unknown = set(names) - {s.name for s in SCENARIOS}
    if unknown:
        print(f"unknown scenario(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    chosen = [s for s in SCENARIOS if not names or s.name in names]
    measurements = [m for scenario in chosen for m in _run_scenario(scenario)]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{datetime.now():%Y%m%dT%H%M%S}.json"
    out.write_text(json.dumps([asdict(m) for m in measurements], indent=2))
    print(_table(measurements))
    print(f"\nraw results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
