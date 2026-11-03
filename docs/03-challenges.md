# Routing across architectures: challenges

CSCS keeps Beverin (AMD MI300) behind its own FirecREST instance, separate from
Clariden (NVIDIA GH200), on purpose. This project leaves that separation alone and
puts the routing in the client, where the tool knows what each job needs. These are
the points the routing has to handle, and how `mc` treats each one today.

| Challenge | Why it matters | In `mc` |
|---|---|---|
| **Software is per architecture** | A CUDA image, an `sglang_base.toml` env or FP8 kernels built for Hopper do not run on MI300; ROCm builds (`*_rocm.toml`) do not run on GH200. Today the mistake surfaces only after the job queued and the container started. | A job spec lists its variants per `arch`; a cluster without a matching variant is **rejected before submission** (`spec.py`, `experiment.py`). |
| **Separate instances, separate OIDC clients** | Each instance trusts its own client. A Clariden client against Beverin's URL is a 401; the right client against the wrong system name is a 404. | One profile keeps URL, client env vars and system together (`profiles.py`); `doctor` checks the instance actually serves the profile's system and explains 401/403/404 (`errors.py`). |
| **Instances fail independently** | Beverin's instance has answered `503 ssh service unhealthy` while Clariden's was fine. A sequential per-cluster script stalls on retries or aborts. | Clusters are checked and run concurrently, each with its own timeout and retries; one being down is a result row, not a crash (`router.py`, `experiment.py`). |
| **Job IDs are per cluster** | `12345` on Clariden and `12345` on Beverin are different jobs; logs, status and cancel need both parts. | Every job is a `QualifiedJobId` (`mock-amd:12345`) everywhere (`jobs.py`). |
| **Partitions, accounts, sizing differ** | `normal` vs `mi300`; 4 × 96 GB vs 4 × 128 GB unified HBM per node, so node counts for a model differ. | Partition and account live in the profile. Sizing is **not handled yet**: `model-launch-factory` sizes per target; that logic should read the profile's node memory. |
| **Storage is partly shared** | capstor is shared (weights downloaded once can serve both), `$SCRATCH` and working directories are not. Downloads currently run on Clariden's `xfer`, so a Clariden outage blocks them even when Beverin is up. | `working_dir` is per profile. Cross-cluster staging is out of scope for the hackathon. |
| **Credentials multiply** | N clusters × M services means N×M client secrets to provision and rotate. | Unchanged: the registry only names the variables. A single cross-instance client is a CSCS-side decision. |
| **Choosing a cluster automatically** | "Run wherever an AMD node is free" needs queue information. | `--arch` selects all fitting clusters; picking the *least busy* one is a natural next step (FirecREST exposes partitions and jobs). |

## What the mock clusters cannot show

Both mock clusters are daint behind one instance. They differ in OIDC client,
architecture tag and injected faults, but they list the same systems, and the
"AMD" one runs on NVIDIA hardware: the probe job is told its pretend
architecture through `MOCK_CLUSTER_ARCH`. A mismatched variant therefore fails
in the probe after a simulated container start (`MOCK_STARTUP_SEC`), not
because ROCm is missing.
