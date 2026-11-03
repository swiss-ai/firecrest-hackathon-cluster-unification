# 4. Known weaknesses and future work

The goal of this version is a minimal, **absolute** improvement: `mc run` must never do worse
than the per-cluster workflow. Where an earlier version did (the pre-submit health check made an
outage take 31.6 s instead of 12 s), it was removed. What remains below is either unchanged from
today or out of scope for the minimal version.

## Same as today (not improved yet)

| Weakness | Today | `mc` now | Possible fix |
|---|---|---|---|
| **Flaky submit** | One 503 on `submit` fails that cluster's run. | Same, but reported as `unreachable: submit failed: instance unhealthy (503)` instead of a traceback. | Submit-or-adopt, as in `sml`'s `_submit_or_adopt`: after a transient error, look the job up by a unique name and adopt it; only resubmit if it is not there. Needs a unique `--job-name` per run. |
| **Per-instance access** | An app must be subscribed to each instance in the Developer Portal. | Same; `mc doctor` says which cluster lacks it. | CSCS side: one endpoint or one subscription for all instances. |
| **Secrets per instance** | N clusters × M services client secrets. | Same; the registry only names the variables. | CSCS side, or a service account with one API key per platform. |

## Out of scope for the minimal version

| Gap | Effect | Possible fix |
|---|---|---|
| **One partition per profile** | Job types needing another partition (Clariden `xfer` for downloads, `debug` for tests) need another profile, so profiles multiply with job types. | Job specs request a partition *kind* (`gpu`, `xfer`, `debug`); profiles map kinds to their own partition names. |
| **No queue-aware choice** | `--arch amd` runs on *every* AMD cluster, not the least busy one. | Use FirecREST's partition and job listings to pick one. |
| **Waiting is fixed** | `--max-wait` applies to the whole wait, queue and run alike; a long job can be cancelled while running. | Separate limits for pending and running time. |
| **Pending reason lost on cancel** | Slurm forgets why a job waited once it is cancelled. | Now reported in the timeout message (`still PENDING (Priority) after …`); could also be shown live. |
| **Sizing per architecture** | 4 × 96 GB (GH200) vs 4 × 128 GB (MI300A) per node changes node counts for a model. | Profile carries node memory; sizing (as in `model-launch-factory`) reads it. |
| **Staging across clusters** | Working dirs and `$SCRATCH` are per cluster; capstor is shared. | Stage per profile; reuse capstor where both clusters see it. |
| **`sml`, `evals-svc`, factory** | Each still has its own per-cluster configuration. | Step 4: bring the registry into `sml` first; the others can then reuse it. |

## Found along the way

- `sml` stores FirecREST secrets under one fixed keyring key, so two configs overwrite each other's
  credentials (step 1). Worth fixing in `sml` independently of this project.
- `sml`'s older branches crash on Clariden's `userinfo` (`KeyError: 'group'`); fixed on `main`.
- FirecREST's `userinfo` truncates long account names (`f7t-hack-+`).
