#!/usr/bin/env bash
# Reproduce, with the real `sml`, what using one tool against several FirecREST
# instances looks like today. Nothing is submitted: `sml advanced --output-script`
# goes through the whole FirecREST setup (auth, system list, partitions) and then
# only renders the job scripts.
#
#   set -a; source .env; set +a
#   baseline/sml_repro.sh /path/to/model-launch   # a checkout of swiss-ai/model-launch
#
# Everything sml writes (configs, keyring, rendered scripts) goes to a temp dir
# that is deleted on exit (its keyring holds the secrets in plaintext); your real
# ~/.sml and system keyring are not touched.
set -uo pipefail

SML_REPO=${1:?usage: $0 /path/to/model-launch}
: "${MOCK_NV_CLIENT_ID:?source .env first}" "${MOCK_AMD_CLIENT_ID:?}" "${HACKATHON_ACCOUNT:?}"

DAINT_URL=https://api.cscs.ch/hpc/firecrest/v2
CLARIDEN_URL=https://api.cscs.ch/ml/firecrest/v2
BEVERIN_URL=https://api.svc.cscs.ch/beverin/firecrest/v2
TOKEN_URI=https://auth.cscs.ch/auth/realms/firecrest-clients/protocol/openid-connect/token

SANDBOX=$(mktemp -d -t sml-repro-XXXX)
trap 'rm -rf "$SANDBOX"' EXIT
export PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring XDG_DATA_HOME="$SANDBOX/keyring"
export SML_SWISSAI_RESEARCH_API_KEY=unused SML_CLUSTER_SSH_HOST=

sml() { uv run --project "$SML_REPO" sml "$@" </dev/null; }

# One `sml init` per cluster: URL, token URI, client ID, client secret.
init() {
    local name=$1 url=$2 client_id=$3 client_secret=$4
    SML_CONFIG_DIR="$SANDBOX/$name" SML_FIRECREST_CLIENT_ID=$client_id SML_FIRECREST_CLIENT_SECRET=$client_secret \
        sml init --launcher firecrest --firecrest-url "$url" --firecrest-token-uri "$TOKEN_URI" >/dev/null 2>&1
}

# Render (not submit) a launch on SYSTEM using CONFIG; print the outcome in one line.
render() {
    local config=$1 system=$2 started=$SECONDS
    local out
    out=$(SML_CONFIG_DIR="$SANDBOX/$config" sml advanced \
        --framework sglang --environment "$SML_REPO/src/swiss_ai_model_launch/assets/envs/sglang_base.toml" \
        --framework-args "--model-path /none --served-model-name t/probe --host 0.0.0.0" \
        --system "$system" --partition normal --reservation firecrest --account "$HACKATHON_ACCOUNT" \
        --output-script "$SANDBOX/out-$config-$system" 2>&1)
    local code=$?
    local last
    last=$(grep -E "Error|Exception|Wrote" <<<"$out" | tail -1 | cut -c1-200)
    printf '  exit=%s %ss  %s\n' "$code" $((SECONDS - started)) "$last"
}

stored_client() {
    uv run --project "$SML_REPO" python -c \
        'import keyring; print(keyring.get_password("swiss_ai_model_launch", "firecrest_client_id"))'
}

echo "1. Configure two clusters, one sml config each (SML_CONFIG_DIR)"
init mock-nv "$DAINT_URL" "$MOCK_NV_CLIENT_ID" "$MOCK_NV_CLIENT_SECRET"
init mock-amd "$DAINT_URL" "$MOCK_AMD_CLIENT_ID" "$MOCK_AMD_CLIENT_SECRET"
case "$(stored_client)" in
    "$MOCK_AMD_CLIENT_ID") echo "  keyring now holds mock-amd's client: mock-nv's credentials were silently overwritten" ;;
    "$MOCK_NV_CLIENT_ID") echo "  keyring holds mock-nv's client" ;;
    *) echo "  keyring holds neither client" ;;
esac

echo "2. Launch on the configured instance's own system"
render mock-nv daint

echo "3. Name a system served by another instance"
render mock-nv clariden
render mock-nv beverin

echo "4. Point sml at the other real instances (sml's default URL is Clariden's /ml/)"
init clariden "$CLARIDEN_URL" "$MOCK_NV_CLIENT_ID" "$MOCK_NV_CLIENT_SECRET"
render clariden clariden
init beverin "$BEVERIN_URL" "$MOCK_NV_CLIENT_ID" "$MOCK_NV_CLIENT_SECRET"
render beverin beverin
