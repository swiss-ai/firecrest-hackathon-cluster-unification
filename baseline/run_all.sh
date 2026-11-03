#!/usr/bin/env bash
# Run the probe on every mock cluster the way a user does today: one cluster at a
# time, swapping the whole FirecREST environment in between, and remembering
# which software variant (IMAGE_ARCH) goes with which cluster.
#
#   IMAGE_ARCH_MOCK_NV=nvidia IMAGE_ARCH_MOCK_AMD=amd baseline/run_all.sh
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
started=$SECONDS
failures=0

run() {
    local cluster=$1 image_arch=$2
    (
        # shellcheck source=/dev/null
        source "${here}/env/${cluster}.env"
        IMAGE_ARCH="${image_arch}" uv run --project "${here}/.." python "${here}/run_on_cluster.py"
    ) || failures=$((failures + 1))
}

run mock-nv "${IMAGE_ARCH_MOCK_NV:-nvidia}"
run mock-amd "${IMAGE_ARCH_MOCK_AMD:-amd}"

echo "{\"total_wall_sec\": $((SECONDS - started)), \"failed_clusters\": ${failures}}"
exit "${failures}"
