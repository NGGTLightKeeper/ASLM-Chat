"""
hardware.py — One-time hardware capability probe.

Detects available GPU/VRAM at startup and returns a profile string
used by ContentProcessor and WebSearchService to decide which optional
inference layers (semantic embeddings, GLiNER) to enable.

Profiles
--------
full_gpu     — CUDA available, >= 4 GB free VRAM
partial_gpu  — CUDA available, 1–4 GB free VRAM (embeddings yes, GLiNER no)
cpu_safe     — No CUDA or < 1 GB free VRAM (BM25 only, no heavy models)

Public API
----------
get_hardware_profile() -> str   (cached; call freely)
"""

from __future__ import annotations

import logging

logger = logging.getLogger("core.config.hardware")

_VRAM_FULL_GB = 4.0    # GB free → full_gpu
_VRAM_PARTIAL_GB = 1.0  # GB free → partial_gpu

_profile_cache: str | None = None


def detect_hardware_profile() -> str:
    """Probe hardware and return a profile string. Not cached; use get_hardware_profile()."""
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


def get_hardware_profile() -> str:
    """Return cached hardware profile (probed once per process lifetime)."""
    global _profile_cache
    if _profile_cache is None:
        _profile_cache = detect_hardware_profile()
        logger.info("hardware profile: %s", _profile_cache)
    return _profile_cache
