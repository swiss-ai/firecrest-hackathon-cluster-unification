"""Run the probe job on ONE cluster, configured the way today's tools are.

Like ``sml``, ``evals-svc`` and ``model-launch-factory``, this knows a single
FirecREST endpoint at a time: URL, credentials, system, partition and the
software variant all come from the environment, and choosing another cluster
means swapping that environment (see ``run_all.sh``). Nothing checks that those
values belong together.

Prints one JSON summary line and exits non-zero when the job did not succeed.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import firecrest as f7t

from multicluster.faults import install_faults
from multicluster.retry import with_retry

PROBE_SCRIPT = Path(__file__).resolve().parent.parent / "jobs" / "probe.sbatch"
POLL_SEC = 5.0
TERMINAL_STATES = frozenset({"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL"})


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"{name} is not set; source this cluster's env file first")
    return value


def _build_client() -> f7t.v2.AsyncFirecrest:
    client = f7t.v2.AsyncFirecrest(
        firecrest_url=_env("FIRECREST_URL"),
        authorization=f7t.ClientCredentialsAuth(
            client_id=_env("FIRECREST_CLIENT_ID"),
            client_secret=_env("FIRECREST_CLIENT_SECRET"),
            token_uri=_env("FIRECREST_TOKEN_URI"),
            min_token_validity=180,
        ),
    )
    install_faults(client, rate=float(os.environ.get("MOCK_FAULT_RATE", "0")))
    return client


async def _wait_for_end(client: f7t.v2.AsyncFirecrest, system: str, job_id: str) -> str:
    while True:
        jobs = await with_retry(lambda: client.job_info(system_name=system, jobid=job_id))
        # Right after submission the job may not be listed yet; Slurm may append detail.
        state = str(jobs[0]["status"]["state"]).split()[0] if jobs else "PENDING"
        if state in TERMINAL_STATES:
            return state
        await asyncio.sleep(POLL_SEC)


async def main() -> int:
    started = time.monotonic()
    client = _build_client()
    system = _env("FIRECREST_SYSTEM")
    working_dir = _env("WORKING_DIR")
    job_env = {"IMAGE_ARCH": os.environ.get("IMAGE_ARCH", "any")}
    if mock_arch := os.environ.get("MOCK_CLUSTER_ARCH"):
        job_env["MOCK_CLUSTER_ARCH"] = mock_arch

    report = await client.submit(
        system_name=system,
        working_dir=working_dir,
        script_str=PROBE_SCRIPT.read_text(),
        env_vars=job_env,
        account=os.environ.get("FIRECREST_ACCOUNT"),
        partition=os.environ.get("FIRECREST_PARTITION"),
        reservation=os.environ.get("FIRECREST_RESERVATION") or None,
    )
    job_id = str(report["jobId"])
    state = await _wait_for_end(client, system, job_id)
    stdout_path = f"{working_dir}/mc-probe-{job_id}.out"
    output = await with_retry(lambda: client.view(system_name=system, path=stdout_path))

    print(
        json.dumps(
            {
                "cluster": os.environ.get("CLUSTER_LABEL", system),
                "job_id": job_id,
                "state": state,
                "wall_sec": round(time.monotonic() - started, 1),
                "output": output.strip(),
            }
        )
    )
    return 0 if state == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
