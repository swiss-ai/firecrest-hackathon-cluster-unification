#!/bin/bash
#SBATCH --job-name=mc-probe
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:05:00
#SBATCH --output=mc-probe-%j.out
#
# Reports which architecture the job landed on. A job carries IMAGE_ARCH (what
# its software was built for). The mock clusters all run on daint, so a mock
# cluster states the hardware it pretends to be in MOCK_CLUSTER_ARCH; real
# clusters leave it unset and the probe detects the GPU vendor.
set -euo pipefail

detect_arch() {
    if command -v nvidia-smi >/dev/null 2>&1; then echo nvidia
    elif command -v rocm-smi >/dev/null 2>&1; then echo amd
    else echo cpu
    fi
}

cluster_arch="${MOCK_CLUSTER_ARCH:-$(detect_arch)}"
image_arch="${IMAGE_ARCH:-any}"
startup_sec="${MOCK_STARTUP_SEC:-20}"

echo "MC_RESULT host=$(hostname) machine=$(uname -m) cluster_arch=${cluster_arch} image_arch=${image_arch}"

if [[ "${image_arch}" != "any" && "${image_arch}" != "${cluster_arch}" ]]; then
    # A real CUDA image on an AMD node fails only once the container starts and
    # the framework initialises its kernels, after the job already waited in
    # the queue and held a node.
    sleep "${startup_sec}"
    echo "MC_ERROR image built for ${image_arch} cannot run on ${cluster_arch}" >&2
    exit 1
fi

echo "MC_OK"
