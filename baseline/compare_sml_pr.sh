#!/usr/bin/env bash
# Run the same steps with sml from main and from the multi-cluster PR
# (swiss-ai/model-launch#279), and report:
#
#   A. no regression: with only `sml init`, both render byte-identical job scripts;
#   B. the improvement: working on Clariden and daint alternately, the number of
#      `sml init` runs and failed launches each needs.
#
# Nothing is submitted (`sml advanced --output-script` only renders). Each sml gets
# its own temporary config and keyring, deleted on exit; ~/.sml and your system
# keyring are not touched.
#
#   set -a; source .env; set +a
#   baseline/compare_sml_pr.sh ~/Projects/model-launch-main ~/Projects/model-launch-multi-cluster
set -uo pipefail

MAIN_REPO=${1:?usage: $0 MAIN_CHECKOUT PR_CHECKOUT}
PR_REPO=${2:?usage: $0 MAIN_CHECKOUT PR_CHECKOUT}
: "${CLARIDEN_CLIENT_ID:?source .env first}" "${CLARIDEN_CLIENT_SECRET:?}"
: "${MOCK_NV_CLIENT_ID:?}" "${MOCK_NV_CLIENT_SECRET:?}" "${HACKATHON_ACCOUNT:?}"
for repo in "$MAIN_REPO" "$PR_REPO"; do
    grep -q swiss-ai-model-launch "$repo/pyproject.toml" 2>/dev/null || { echo "$repo is not a model-launch checkout" >&2; exit 2; }
done
if ! grep -q "def register_system" "$PR_REPO/src/swiss_ai_model_launch/cli/configuration/system_init.py" 2>/dev/null; then
    echo "$PR_REPO does not have the PR's 'sml init --system' (check out feat/multi-cluster-endpoints)" >&2
    exit 2
fi

CLARIDEN_URL=https://api.cscs.ch/ml/firecrest/v2
DAINT_URL=https://api.cscs.ch/hpc/firecrest/v2
TOKEN_URI=https://auth.cscs.ch/auth/realms/firecrest-clients/protocol/openid-connect/token

SANDBOX=$(mktemp -d -t sml-compare-XXXX)
trap 'rm -rf "$SANDBOX"' EXIT
export PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring
export SML_SWISSAI_RESEARCH_API_KEY=unused SML_CSCS_API_KEY=unused SML_CLUSTER_SSH_HOST=
unset SML_SYSTEM SML_PARTITION

# Per tool: its repo, venv, config dir and keyring; counters for the summary.
declare -A REPO=([main]=$MAIN_REPO [pr]=$PR_REPO) INITS=([main]=0 [pr]=0) FAILS=([main]=0 [pr]=0)

sml() {
    local tool=$1; shift
    UV_PROJECT_ENVIRONMENT="$HOME/.venvs/sml-compare-$tool" XDG_DATA_HOME="$SANDBOX/$tool/keyring" \
        SML_CONFIG_DIR="$SANDBOX/$tool/config" uv run --quiet --project "${REPO[$tool]}" sml "$@" </dev/null
}

init() {  # init TOOL URL CLIENT_ID CLIENT_SECRET [extra sml init args]
    local tool=$1 url=$2 id=$3 secret=$4; shift 4
    INITS[$tool]=$((INITS[$tool] + 1))
    SML_FIRECREST_CLIENT_ID=$id SML_FIRECREST_CLIENT_SECRET=$secret \
        sml "$tool" init --launcher firecrest --firecrest-url "$url" --firecrest-token-uri "$TOKEN_URI" "$@" \
        >/dev/null 2>&1 || echo "    [$tool] sml init failed"
}

render() {  # render TOOL SYSTEM OUT_DIR -> prints one line, counts failures
    local tool=$1 system=$2 out_dir=$3 out code summary
    local -a extra=(--partition normal)
    [[ $system == daint ]] && extra+=(--account "$HACKATHON_ACCOUNT" --reservation firecrest)
    [[ $system == clariden ]] && extra=(--partition debug)
    out=$(sml "$tool" advanced --framework sglang \
        --environment "${REPO[$tool]}/src/swiss_ai_model_launch/assets/envs/sglang_base.toml" \
        --framework-args "--model-path /none --served-model-name t/probe --host 0.0.0.0" \
        --system "$system" "${extra[@]}" --output-script "$out_dir" 2>&1)
    code=$?
    summary=$(grep -E "Error|Exception|Wrote" <<<"$out" | tail -1)
    [[ $code -eq 0 ]] || FAILS[$tool]=$((FAILS[$tool] + 1))
    printf '    [%-4s] --system %-8s exit=%s  %s\n' "$tool" "$system" "$code" "${summary:0:110}"
}

# Rendered scripts embed the checkout's own path (env TOML) and a random job-name
# suffix; mask both so that only real differences remain.
normalized() {  # normalized TOOL DIR
    local tool=$1 dir=$2 f
    for f in "$dir"/*; do
        echo "== ${f##*/}"
        sed -E -e "s|${REPO[$tool]%/}|<checkout>|g" -e 's/(--job-name=.*_)[A-Za-z]{8}$/\1XXXXXXXX/' "$f"
    done
}

echo "A. No regression: same sml init, same launch, on main and on the PR"
for tool in main pr; do
    init "$tool" "$CLARIDEN_URL" "$CLARIDEN_CLIENT_ID" "$CLARIDEN_CLIENT_SECRET"
    render "$tool" clariden "$SANDBOX/$tool/regression"
done
if differences=$(diff <(normalized main "$SANDBOX/main/regression") <(normalized pr "$SANDBOX/pr/regression")); then
    echo "    rendered job scripts are identical (checkout path and job-name suffix masked)"
else
    echo "    rendered job scripts DIFFER:"; head -20 <<<"$differences"
fi
INITS=([main]=0 [pr]=0) FAILS=([main]=0 [pr]=0)

echo "B. Work on daint, clariden, daint, clariden (main instance: Clariden)"
echo "  main: one instance per config, so every switch is an sml init"
render main daint "$SANDBOX/main/b1"                         # without re-init: rejected
init main "$DAINT_URL" "$MOCK_NV_CLIENT_ID" "$MOCK_NV_CLIENT_SECRET"
render main daint "$SANDBOX/main/b2"
render main clariden "$SANDBOX/main/b3"                      # forgot to switch back: rejected
init main "$CLARIDEN_URL" "$CLARIDEN_CLIENT_ID" "$CLARIDEN_CLIENT_SECRET"
render main clariden "$SANDBOX/main/b4"
init main "$DAINT_URL" "$MOCK_NV_CLIENT_ID" "$MOCK_NV_CLIENT_SECRET"
render main daint "$SANDBOX/main/b5"
init main "$CLARIDEN_URL" "$CLARIDEN_CLIENT_ID" "$CLARIDEN_CLIENT_SECRET"
render main clariden "$SANDBOX/main/b6"

echo "  pr: add daint once, then just pick the system"
INITS[pr]=$((INITS[pr] + 1))
SML_FIRECREST_CLIENT_ID=$MOCK_NV_CLIENT_ID SML_FIRECREST_CLIENT_SECRET=$MOCK_NV_CLIENT_SECRET \
    sml pr init --system daint >/dev/null 2>&1 || echo "    [pr  ] sml init --system daint failed"
for system in daint clariden daint clariden; do render pr "$system" "$SANDBOX/pr/b-$system-$RANDOM"; done

echo
echo "Summary for B (4 launches wanted, after the initial sml init)"
printf '  %-5s  sml init runs: %s   failed launches: %s\n' main "${INITS[main]}" "${FAILS[main]}"
printf '  %-5s  sml init runs: %s   failed launches: %s\n' pr "${INITS[pr]}" "${FAILS[pr]}"
