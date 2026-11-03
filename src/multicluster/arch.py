"""Accelerator architectures a cluster can have and a job can be built for."""

from enum import Enum


class Arch(str, Enum):
    """GPU vendor family; it decides which images, envs and kernels a job may use.

    Clariden is NVIDIA (GH200) and Beverin is AMD (MI300), which is why they sit
    behind separate FirecREST instances in the first place.
    """

    NVIDIA = "nvidia"
    AMD = "amd"

    def __str__(self) -> str:
        return self.value
