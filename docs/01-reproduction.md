# 1. Reproducing the per-cluster workflow

Run on 2026-11-03 against daint (`https://api.cscs.ch/hpc/firecrest/v2`), reservation
`firecrest`, account `f7t-hack-course2026-cscs`, with two Developer Portal apps standing in for
Clariden's and Beverin's separate OIDC clients (see the README for the mock setup).

The baseline (`baseline/run_all.sh`) does what a user of `sml` / `evals-svc` does today: for each
cluster, load that cluster's environment (URL, client, system, partition, account, software
variant), run, then swap to the next one.

## Run it yourself

```bash
set -a; source .env; set +a                          # credentials, account, scratch
bash baseline/run_all.sh                             # happy path
IMAGE_ARCH_MOCK_AMD=nvidia bash baseline/run_all.sh  # wrong variant for the AMD cluster
MOCK_AMD_FAULT_RATE=0.3 bash baseline/run_all.sh     # flaky AMD instance
MOCK_AMD_FAULT_RATE=1 bash baseline/run_all.sh       # AMD instance down
```

Each line prints one JSON line per cluster and a total; the exit code is the number of failed clusters.

## What happened

| Scenario | Result | Total wall | What it shows |
|---|---|---|---|
| Happy path | both `COMPLETED` (jobs 5245816, 5245818) | 23 s | Works, but strictly sequential: total = sum of clusters (11.4 s + 11.2 s). |
| Wrong variant (CUDA build sent to the AMD cluster) | mock-amd `FAILED` after **32.3 s** (job 5245825) | 45 s | Nothing checks the variant against the cluster. The job is accepted, queues, takes a node, starts, and only then fails. With a real model this is the queue wait plus container start plus weight loading, not 32 s. |
| Flaky instance (30 % of AMD requests answer 503) | mock-amd **crashed with a traceback** on submit | 12 s | One 503 on the submit call ends that cluster's run. Submission is deliberately not retried (FirecREST can report an error for an sbatch that went through), as in `sml`. |
| AMD instance down | mock-amd crashed with a traceback | 12 s | Same: a raw `UnexpectedStatusException`, no indication of which cluster or what to do. |

Also observed while setting this up:

- **Without the reservation the job sat `PENDING (Priority)`** in daint's normal queue (job 5245726),
  while the same job with `--reservation=firecrest` started at once. Reservation is one more
  per-cluster setting (Clariden has `APP_CLARIDEN_RESERVATION` in `model-launch-factory`).
- **FirecREST truncates the account name** in `userinfo` (`f7t-hack-+`); the full name
  (`f7t-hack-course2026-cscs`) had to be confirmed by submitting a job with it.
- **Job IDs carry no cluster.** The output says `5245818`; following it up later requires knowing it
  was submitted through the mock-amd environment.

## How big is the problem?

On the mock the absolute numbers are small because the probe is tiny and both "clusters" are the
same idle reservation. What scales with real workloads:

1. **Sequential cost.** Total time is the sum over clusters; a slow or retrying cluster delays the rest.
2. **Late failures.** A variant/architecture mismatch costs a full queue wait and node allocation per attempt.
3. **Fragility.** One unhealthy instance turns into a crash for that cluster, with an error that names neither the cluster nor the fix.
4. **Configuration surface.** Per cluster: URL, token URI, client ID, client secret, system, partition,
   account, reservation, working dir, software variant (10 values, in each tool, kept consistent by hand).

## What the mock does not show

Both apps reach the same daint instance, so using mock-nv's client with mock-amd's environment
succeeds here, whereas against real Clariden/Beverin it would be a 401. See
[03-challenges.md](03-challenges.md#what-the-mock-clusters-cannot-show).
