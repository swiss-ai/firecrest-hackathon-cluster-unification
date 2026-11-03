# 5. The same idea in `sml`: model-launch#279

[swiss-ai/model-launch#279](https://github.com/swiss-ai/model-launch/pull/279) lets one `sml` setup
reach systems on several FirecREST instances:

```bash
sml init                     # main instance, as today (e.g. Clariden)
sml init --system beverin    # once: an app subscribed to Beverin's instance
sml advanced --system beverin ...   # then just pick the system
sml advanced --system clariden ...
```

## Proof: main vs the PR, same steps

```bash
set -a; source .env; set +a
baseline/compare_sml_pr.sh ~/Projects/model-launch-main ~/Projects/model-launch-multi-cluster
```

Run on 2026-11-03 (main `dc10d59`, PR `a3f6093`), nothing submitted:

| Check | main | PR |
|---|---|---|
| A. Existing setup (only `sml init` for Clariden), render a Clariden launch | rendered | **byte-identical** job scripts (checkout path and random job-name suffix masked) |
| B. Launch on daint, clariden, daint, clariden after the initial `sml init` | **4** `sml init` runs, **2** failed launches (`Valid options: ['clariden', 'bristen']`, then `['eiger', 'daint']`) | **1** `sml init --system daint`, **0** failures |

A shows that nothing changes for anyone who does not add a system; B is the improvement.

## Downsides and limits

- **Hard-coded instance URLs.** If CSCS moves an instance, `sml` needs a release; until then
  `sml init --system NAME --firecrest-url URL` overrides it.
- **Credentials per system, not per instance.** `eiger` shares daint's instance but needs its own
  `sml init --system eiger`; until then it behaves as today.
- **Needs a keyring** for `sml init --system`, like `sml init`; without one, `clusters.yml` can name
  environment variables instead.
- **Still one Developer Portal subscription per instance**; only CSCS can change that.
- **More code**: one module (~170 lines), one init flow (~70 lines), and their tests.
- **Not exercised on Beverin** (no app subscribed to it during the hackathon) and not with a real
  submission (rendering goes through the same FirecREST client and calls up to `sbatch`).
