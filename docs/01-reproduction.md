# 1. Reproducing today's multi-cluster workflow

Run on 2026-11-03 with the real `sml` (swiss-ai/model-launch `origin/main`, `dc10d59`) against
two working FirecREST instances, each reached through its own Developer Portal app, as Clariden
and Beverin are today:

| Instance | URL | App | Serves |
|---|---|---|---|
| HPC platform | `https://api.cscs.ch/hpc/firecrest/v2` | hackathon app (`course_4126c16c`) | `daint`, `eiger` |
| ML platform | `https://api.cscs.ch/ml/firecrest/v2` | Swiss AI app, subscribed to this instance only | `clariden`, `bristen` |
| Beverin | `https://api.svc.cscs.ch/beverin/firecrest/v2` | (no app subscribed) | `beverin` |

## Run it yourself

```bash
set -a; source .env; set +a
baseline/sml_repro.sh ~/Projects/model-launch     # your checkout; ~1 min, nothing is submitted
```

`sml advanced --output-script` performs the whole FirecREST part of a launch (token, system list,
partitions, path checks) and then only renders the job scripts, so no node is used. Configs and
keyring go to a temporary sandbox that is deleted on exit.

## What happens

| # | Step | Result |
|---|---|---|
| 1 | `sml init` for daint, render a launch; `sml init` for Clariden (separate `SML_CONFIG_DIR`), render a launch | Both work (2–3 s on daint, 13 s on Clariden). |
| 2 | Go back to the daint config **without** re-running init | **403 `API Subscription validation failed`**. `sml` keeps secrets under one fixed keyring key (`swiss_ai_model_launch` / `firecrest_client_id`), so the Clariden init overwrote daint's credentials; the daint config now sends the Clariden app to daint's instance. |
| 3 | Switch properly: `sml init` again before every switch | Works, at the price of a full re-init (URL, token URI, client ID, secret) on **every** switch. |
| 4 | From the Clariden config, `--system daint` / `--system beverin` | `ValueError: Invalid value 'daint' for --system. Valid options: ['clariden', 'bristen']`. A config sees only the systems of its own instance. |
| 5 | Beverin's URL with the Clariden app | **403 `API Subscription validation failed`**. A third instance needs a third subscription in the portal. |

## What this means in practice

Take validating a new Apertus checkpoint on Clariden (GH200) and Beverin (MI300) with `sml`:

- two instance URLs to know (nothing lists them), and an app **subscribed to each instance's API**;
- `sml init` before **every** switch between them, because configs share one credential slot;
  forgetting it is a 403 against your own config, as in step 2;
- per instance: system name, partition (`normal` vs `mi300`), account, reservation, and the
  CUDA vs ROCm environment, all remembered by the user;
- no way to run, watch or compare both from one command, and errors that are raw tracebacks
  naming neither the cluster nor the setting that is wrong.

Two further findings from setting up daint:

- Without `--reservation=firecrest` the probe job sat `PENDING (Priority)` (job 5245726); with it,
  it started at once. Reservation is one more per-cluster setting.
- FirecREST's `userinfo` truncates the account (`f7t-hack-+`); the full name
  (`f7t-hack-course2026-cscs`) had to be confirmed by submitting a job.

## What this step does not cover

- **Architecture.** Separate instances do not by themselves stop a CUDA build from reaching an AMD
  cluster; that is a routing concern, measured in step 2 (`bench/measure.py`, `wrong-variant`).
- **Flaky instances.** The 503 scenarios are injected (`multicluster/faults.py`) and belong to step 2.
- **Beverin itself.** No app is subscribed to it, so it stops at the 403.

`baseline/run_all.sh` remains as the script-based baseline that step 2 benchmarks `mc` against.
