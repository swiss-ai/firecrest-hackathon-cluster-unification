# 1. Reproducing today's multi-cluster workflow

Run on 2026-11-03 with the real `sml` (swiss-ai/model-launch `origin/main`, `dc10d59`), two
Developer Portal apps (`hackathon-mock-nv`, `hackathon-mock-amd`) subscribed to daint's FirecREST,
and the hackathon account `course_4126c16c`.

## Run it yourself

```bash
set -a; source .env; set +a
baseline/sml_repro.sh /path/to/model-launch     # ~10 s, nothing is submitted
```

`sml advanced --output-script` performs the whole FirecREST part of a launch (token, system list,
partitions) and then only renders the job scripts, so no node is used. Configs and keyring go to
a temporary sandbox that is deleted on exit.

## What happens

| # | Step | Result |
|---|---|---|
| 1 | `sml init` once per cluster, each in its own `SML_CONFIG_DIR` | Both report success, but `sml` keeps secrets in the keyring under a **fixed key** (`swiss_ai_model_launch` / `firecrest_client_id`), so the second init **silently overwrote the first cluster's credentials**. |
| 2 | Launch on the configured instance's system (`--system daint`) | Works (exit 0, ~2 s). |
| 3 | Same config, `--system clariden` / `--system beverin` | `ValueError: Invalid value 'clariden' for --system. Valid options: ['eiger', 'daint']`. A config can only see the systems of the one instance its URL points at. |
| 4 | Re-init against Clariden's instance (`/ml/`, which is **sml's default URL**) and Beverin's (`api.svc.cscs.ch/beverin/`) with the same app | `403 Resource forbidden: API Subscription validation failed` on both. Every instance is a separate API in the Developer Portal; an app must be subscribed to each one separately, and that is a manual step in the portal. |

## What this means in practice

To work on N clusters with `sml` today a user needs, per cluster:

- the instance URL (three different hosts/paths for daint, Clariden, Beverin; nothing lists them);
- a Developer Portal app, or an existing one, **subscribed to that instance's API**;
- an `sml init` (URL, token URI, client ID, client secret), and a way to switch between configs;
  `SML_CONFIG_DIR` separates the config files but **not the secrets**, so switching clusters means
  re-entering credentials or exporting `SML_FIRECREST_CLIENT_*` by hand every time;
- the system name, partition, account and reservation valid on that instance.

And the tool gives no help when they don't match: a wrong system is a Python traceback ending in
`ValueError`, a wrong instance is a traceback ending in a raw 403 body. Neither says which cluster
or which setting is off.

Two further findings from setting up daint:

- Without `--reservation=firecrest` the probe job sat `PENDING (Priority)` (job 5245726), with it,
  it started at once: reservation is one more per-cluster setting.
- FirecREST's `userinfo` truncates the account (`f7t-hack-+`); the full name
  (`f7t-hack-course2026-cscs`) had to be confirmed by submitting a job.

## What this step does not cover

- **Architecture.** Separate instances do not by themselves stop a CUDA build from reaching an AMD
  cluster; that is a routing concern, measured in step 2 (`bench/measure.py`, `wrong-variant`).
- **Flaky instances.** The 503 scenarios are injected (`multicluster/faults.py`) and also belong to
  step 2.
- **A real cross-instance job.** The course apps are only subscribed to daint, so Clariden and
  Beverin stop at the 403. That is the finding, but it means jobs on them could not be compared.

`baseline/run_all.sh` remains as the script-based baseline that step 2 benchmarks `mc` against.
