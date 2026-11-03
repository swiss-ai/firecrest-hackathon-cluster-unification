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

## Development

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```
