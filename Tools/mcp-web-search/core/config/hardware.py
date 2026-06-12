# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import logging

logger = logging.getLogger("core.config.hardware")

_VRAM_FULL_GB = 4.0    # GB free → full_gpu
_VRAM_PARTIAL_GB = 1.0  # GB free → partial_gpu

_profile_cache: str | None = None


# Probe GPU VRAM once and return full_gpu, partial_gpu, or cpu_safe.
def detect_hardware_profile() -> str:
    try:
        import torch  # type: ignore
        if not torch.cuda.is_available():
            logger.debug("hardware: CUDA not available → cpu_safe")
            return "cpu_safe"

        free_bytes, _ = torch.cuda.mem_get_info()
        free_gb = free_bytes / (1024 ** 3)
        logger.debug("hardware: CUDA available, free VRAM=%.1f GB", free_gb)

        if free_gb >= _VRAM_FULL_GB:
            return "full_gpu"
        if free_gb >= _VRAM_PARTIAL_GB:
            return "partial_gpu"
        return "cpu_safe"

    except ImportError:
        logger.debug("hardware: torch not installed → cpu_safe")
        return "cpu_safe"
    except Exception as exc:
        logger.warning("hardware probe failed: %s → cpu_safe", exc)
        return "cpu_safe"


# Return cached hardware profile (probed once per process).
def get_hardware_profile() -> str:
    global _profile_cache
    if _profile_cache is None:
        _profile_cache = detect_hardware_profile()
        logger.info("hardware profile: %s", _profile_cache)
    return _profile_cache
