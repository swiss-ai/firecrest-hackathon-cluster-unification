# FirecREST cluster unification

Hackathon project (CSCS FirecREST Hackathon, 2026-11-03).

Swiss AI tools reach each Alps cluster through a separate FirecREST instance: Clariden (NVIDIA GH200)
at `api.cscs.ch/ml/firecrest/v2`, Beverin (AMD MI300) at `api.svc.cscs.ch/beverin/firecrest/v2`, each
with its own OIDC client. Every tool (`sml`, `model-launch-factory`, `evals-svc`) re-implements the
mapping from cluster to URL, credentials and architecture-specific settings, or supports one cluster only.

This repo:

1. reproduces that situation with two mock clusters on daint (`baseline/`, `docs/01-reproduction.md`);
2. embeds a cluster-aware routing layer in a small experiment tool, `mc` (`src/multicluster/`);
3. measures the difference (`bench/`, `docs/02-results.md`).

## Setup

1. Create two applications in the [CSCS Developer Portal](https://developer.svc.cscs.ch/devportal/apis),
   one per mock cluster, both subscribed to daint's FirecREST.
2. Export their credentials and your hackathon account details (never commit them):

   ```bash
   export MOCK_NV_CLIENT_ID=...  MOCK_NV_CLIENT_SECRET=...
   export MOCK_AMD_CLIENT_ID=... MOCK_AMD_CLIENT_SECRET=...
   export HACKATHON_ACCOUNT=...                       # Slurm account
   export HACKATHON_SCRATCH=/capstor/scratch/cscs/$USER # job working directory
   ```

3. `cp clusters.example.toml clusters.toml`
4. If the checkout's `.venv` was created by another user, use your own:
   `export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/firecrest-hackathon"`

## Usage

```bash
# Today's workflow with the real sml (step 1)
baseline/sml_repro.sh /path/to/model-launch

# Script baseline: one cluster at a time, environment swapped in between
baseline/run_all.sh

# Unified
uv run mc doctor
uv run mc run jobs/probe.toml                       # every cluster, its own variant each
uv run mc run jobs/probe.toml --arch amd            # wherever the architecture fits
uv run mc run jobs/probe-cuda-only.toml             # AMD cluster rejected before submission
uv run mc run jobs/probe.toml --fault mock-amd=0.3  # flaky AMD instance
uv run mc status mock-amd:12345

# Both, on the same scenarios
uv run python bench/measure.py
```

See [docs/03-challenges.md](docs/03-challenges.md) for what routing across architectures has to handle.

## Development

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```
