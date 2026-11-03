#!/usr/bin/env bash
# Reproduce, with the real `sml`, what using one tool against several FirecREST
# instances looks like today: daint (hackathon app) and Clariden (Swiss AI app),
# two instances with two URLs and two OIDC clients, plus Beverin's URL.
#
# Nothing is submitted: `sml advanced --output-script` goes through the whole
# FirecREST setup (token, system list, partitions) and then only renders the
# job scripts.
#
#   set -a; source .env; set +a
#   baseline/sml_repro.sh /path/to/model-launch   # a checkout of swiss-ai/model-launch
#
# Needs MOCK_NV_CLIENT_ID/SECRET and HACKATHON_ACCOUNT (daint); CLARIDEN_CLIENT_ID/
# SECRET (and optionally CLARIDEN_ACCOUNT) for the Clariden steps, which are
# skipped otherwise. Everything sml writes (configs, keyring, rendered scripts)
# goes to a temp dir that is deleted on exit (its keyring holds the secrets in
# plaintext); your real ~/.sml and system keyring are not touched.
set -uo pipefail

SML_REPO=${1:?usage: $0 /path/to/model-launch}
: "${MOCK_NV_CLIENT_ID:?source .env first}" "${MOCK_NV_CLIENT_SECRET:?}" "${HACKATHON_ACCOUNT:?}"

DAINT_URL=https://api.cscs.ch/hpc/firecrest/v2
CLARIDEN_URL=https://api.cscs.ch/ml/firecrest/v2
BEVERIN_URL=https://api.svc.cscs.ch/beverin/firecrest/v2
TOKEN_URI=https://auth.cscs.ch/auth/realms/firecrest-clients/protocol/openid-connect/token
ENV_TOML="$SML_REPO/src/swiss_ai_model_launch/assets/envs/sglang_base.toml"

SANDBOX=$(mktemp -d -t sml-repro-XXXX)
trap 'rm -rf "$SANDBOX"' EXIT
export PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring XDG_DATA_HOME="$SANDBOX/keyring"
export SML_SWISSAI_RESEARCH_API_KEY=unused SML_CLUSTER_SSH_HOST=

sml() { uv run --project "$SML_REPO" sml "$@" </dev/null; }

# One `sml init` per cluster: URL, token URI, client ID, client secret.
init() {
    local config=$1 url=$2 client_id=$3 client_secret=$4
    SML_CONFIG_DIR="$SANDBOX/$config" SML_FIRECREST_CLIENT_ID=$client_id SML_FIRECREST_CLIENT_SECRET=$client_secret \
        sml init --launcher firecrest --firecrest-url "$url" --firecrest-token-uri "$TOKEN_URI" >/dev/null 2>&1
    echo "  sml init $config ($url)"
}

# Render (not submit) a launch with CONFIG on SYSTEM/PARTITION; print the outcome in one line.
render() {
    local config=$1 system=$2 partition=$3 account=${4:-} started=$SECONDS out code
    local -a extra=()
    [[ -n "$account" ]] && extra+=(--account "$account")
    [[ "$system" == daint ]] && extra+=(--reservation firecrest)
    out=$(SML_CONFIG_DIR="$SANDBOX/$config" sml advanced \
        --framework sglang --environment "$ENV_TOML" \
        --framework-args "--model-path /none --served-model-name t/probe --host 0.0.0.0" \
        --system "$system" --partition "$partition" "${extra[@]}" \
        --output-script "$SANDBOX/out-$config-$system" 2>&1)
    code=$?
    printf '  [%s config -> %s] exit=%s %ss  %s\n' "$config" "$system" "$code" $((SECONDS - started)) \
        "$(grep -E "Error|Exception|Wrote" <<<"$out" | tail -1 | cut -c1-170)"
}

stored_client() {
    uv run --project "$SML_REPO" python -c \
        'import keyring; print(keyring.get_password("swiss_ai_model_launch", "firecrest_client_id"))'
}

whose_client() {
    case "$(stored_client)" in
        "$MOCK_NV_CLIENT_ID") echo "the daint app" ;;
        "${CLARIDEN_CLIENT_ID:-unset}") echo "the Clariden app" ;;
        *) echo "neither app" ;;
    esac
}

echo "1. One sml config per instance"
init daint "$DAINT_URL" "$MOCK_NV_CLIENT_ID" "$MOCK_NV_CLIENT_SECRET"
render daint daint normal "$HACKATHON_ACCOUNT"
if [[ -z "${CLARIDEN_CLIENT_ID:-}" ]]; then
    echo "  CLARIDEN_CLIENT_ID not set: skipping the cross-instance steps"
    exit 0
fi
init clariden "$CLARIDEN_URL" "$CLARIDEN_CLIENT_ID" "$CLARIDEN_CLIENT_SECRET"
render clariden clariden normal "${CLARIDEN_ACCOUNT:-}"

echo "2. Switch back to daint without re-running init"
echo "  keyring now holds $(whose_client)'s credentials (one slot for every config)"
render daint daint normal "$HACKATHON_ACCOUNT"

echo "3. Switching properly: re-init each time"
init daint "$DAINT_URL" "$MOCK_NV_CLIENT_ID" "$MOCK_NV_CLIENT_SECRET"
render daint daint normal "$HACKATHON_ACCOUNT"
init clariden "$CLARIDEN_URL" "$CLARIDEN_CLIENT_ID" "$CLARIDEN_CLIENT_SECRET"
render clariden clariden normal "${CLARIDEN_ACCOUNT:-}"

echo "4. Name the other instance's system from a config"
render clariden daint normal
render clariden beverin mi300

echo "5. Beverin's instance with the Clariden app"
init beverin "$BEVERIN_URL" "$CLARIDEN_CLIENT_ID" "$CLARIDEN_CLIENT_SECRET"
render beverin beverin mi300 "${CLARIDEN_ACCOUNT:-}"
