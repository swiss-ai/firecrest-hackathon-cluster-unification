# 2. Results: one registry instead of one config per instance

Run on 2026-11-03. Raw data in `results/raw/`: `20261103T142002.json` (all scenarios),
`20261103T142145.json` (flaky and outage, re-run after a benchmark bug), `20261103T144647.json`
(happy and outage, after removing the pre-submit health check).

## The URL and login split

The problem step 1 reproduced: with `sml`, each instance needs its own `sml init`, configs share
one credential slot, and a config can only see its own instance's systems.

| | `sml` today | `mc` |
|---|---|---|
| Reach daint (HPC instance) **and** Clariden (ML instance) | `sml init` per instance, and again on **every** switch; forgetting it is a 403 (step 1, row 2) | One `clusters.toml`; `mc doctor` checked all three clusters on both instances in **0.8 s**, no init |
| Credentials | One keyring slot shared by every config | Per cluster, named in the profile (`client_id_env`), so they never overwrite each other |
| Name a system on another instance | `ValueError: Valid options: ['clariden', 'bristen']` | `--clusters mock-nv,clariden` routes each to its own instance |
| Wrong instance or missing subscription | Traceback ending in a raw 403 body | `DOWN clariden … forbidden: the OIDC client is not subscribed to this instance` |
| Job IDs | `5246154`: which cluster? | `mock-nv:5246154` |

```
$ uv run mc doctor
up   mock-nv        0.29s  daint via https://api.cscs.ch/hpc/firecrest/v2
up   mock-amd       0.16s  daint via https://api.cscs.ch/hpc/firecrest/v2
up   clariden       0.10s  clariden via https://api.cscs.ch/ml/firecrest/v2
```

A real job on both instances, one command (daint with the hackathon app, Clariden `debug` with the
Swiss AI app, account `infra01`):

```
$ uv run mc run jobs/probe.toml --clusters mock-nv,clariden --max-wait 300
completed    mock-nv      mock-nv:5246314           13.4s  COMPLETED
timed-out    clariden     clariden:3842798         310.0s  clariden:3842798 still PENDING after 303 s; cancelled

$ uv run mc run jobs/probe.toml --clusters mock-nv,clariden --max-wait 300    # second try
completed    mock-nv      mock-nv:5246357           12.6s  COMPLETED
completed    clariden     clariden:3842841         306.7s  COMPLETED
```

The first attempt shows the busy Clariden queue handled per cluster: daint's result arrived after
13 s, and Clariden's job was cancelled at the limit instead of waiting indefinitely.

What does **not** change: each instance still needs an app subscribed to it. `mc` removes the
switching, not the one-time access setup; a single endpoint for all clusters is a CSCS-side change.

## Running work on several clusters

Same probe job on the two mock clusters (daint, reservation `firecrest`), baseline
(`baseline/run_all.sh`, one cluster after the other) vs `mc run --clusters mock-nv,mock-amd`:

| Scenario | Baseline | `mc` | Why |
|---|---|---|---|
| Both healthy | both completed, **26.6 s** / 30.7 s | both completed, **11.7 s** / 12.3 s | `mc` runs clusters concurrently; total = slowest cluster, not the sum. |
| CUDA-only job to the AMD cluster | AMD job accepted, ran and **failed after 32 s** on a node; 44.6 s total | AMD **rejected in 0.0 s before submission** (`no amd variant`); NVIDIA completed; 12.8 s total | The job spec declares its variants per architecture; no node is spent on a job that cannot run. |
| AMD instance down (every request 503) | AMD **crashed with a traceback**; 12.5 s | AMD `unreachable: submit failed: instance unhealthy (503)`; NVIDIA completed; **13.3 s** | Same speed, failure reported per cluster in words. (A first version ran a health check before submitting, which retried with backoff and took 31.6 s; it was removed so that `mc run` sends exactly the baseline's requests.) |
| AMD instance flaky (30 % 503) | completed (27.6 s) | AMD `unreachable: submit failed: instance unhealthy (503)` | **Inconclusive**: a single random run. Neither tool retries a submit (FirecREST can fail an sbatch that went through, so a blind retry may duplicate the job), so each succeeds ~70 % of the time. `mc` only makes the failure readable. |

## Caveats

- The two "clusters" in the timing table are the same daint instance and an idle reservation, so
  absolute times are small; the concurrency and early-rejection effects grow with real queue times
  and model start-up.
- The first benchmark run passed `--fault` after `run JOB`, where `mc` does not accept it, so the
  flaky and outage rows of `20261103T142002.json` are usage errors; they were re-run.
- Improving the flaky case would need submit-or-adopt (look the job up by name after a failed
  submit, as `sml`'s `_submit_or_adopt` does). That is a retry-policy improvement, not part of the
  URL unification, and is left out of the minimal version.
- Known weaknesses and next steps are collected in [04-future-work.md](04-future-work.md).
