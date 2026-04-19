# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Overdrive mode configuration loader for deep research."""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass

from services.deep_research.config import ResearchConfig

logger = logging.getLogger("services.deep_research.overdrive_config")

_TOML_FILENAME = "deep_research_overdrive.toml"


def _find_toml() -> pathlib.Path | None:
    candidates = [
        pathlib.Path.cwd() / _TOML_FILENAME,
        pathlib.Path(__file__).parent.parent.parent / _TOML_FILENAME,
        pathlib.Path(__file__).parent.parent.parent.parent / _TOML_FILENAME,
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _load_toml(path: pathlib.Path) -> dict:
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            logger.warning("tomllib/tomli not available; overdrive TOML will not be read")
            return {}
    with open(path, "rb") as fh:
        return tomllib.load(fh)


@dataclass
class OverdriveSettings:
    """Sandbox and file-import settings extracted from overdrive TOML."""

    sandbox_enabled: bool = True
    sandbox_image: str = "dima1312313/mcp-sandbox:latest"
    sandbox_cpu: str = "2"
    sandbox_memory: str = "2g"
    sandbox_memory_swap: str = "3g"
    sandbox_pids_limit: str = "128"

    import_file_enabled: bool = True
    import_file_max_size_mb: int = 100
    import_file_timeout_sec: int = 120


def load_overdrive_config(question: str) -> tuple[ResearchConfig, OverdriveSettings]:
    """Return (ResearchConfig, OverdriveSettings) tuned for overdrive depth."""
    cfg = ResearchConfig.for_question(question)
    settings = OverdriveSettings()

    path = _find_toml()
    if path is None:
        logger.warning("deep_research_overdrive.toml not found; applying built-in overdrive defaults")
        _apply_builtin_defaults(cfg)
        return cfg, settings

    data = _load_toml(path)
    _apply_limits(cfg, data.get("limits", {}))
    _apply_context(cfg, data.get("context", {}))
    _apply_sandbox_backend(cfg, data.get("sandbox", {}))
    _fill_settings(settings, data)

    logger.info("Overdrive config loaded from %s", path)
    return cfg, settings


# ---------------------------------------------------------------------------

def _apply_builtin_defaults(cfg: ResearchConfig) -> None:
    cfg.max_steps = 50
    cfg.max_search_calls = 20
    cfg.max_read_calls = 35
    cfg.max_python_calls = 15
    cfg.max_site_map_calls = 8
    cfg.extra_quota_search_calls = 12
    cfg.extra_quota_read_calls = 12
    cfg.total_timeout_sec = 3600.0
    cfg.synthesis_reserve_sec = 480.0
    cfg.controller_timeout_sec = 120.0
    cfg.max_sources = 150
    cfg.search_results_per_call = 15
    cfg.synthesis_context_budget = 180_000
    cfg.read_page_max_chars = 60_000
    cfg.read_chunk_chars = 10_000
    cfg.read_chunk_overlap = 400
    cfg.tool_observation_max_chars = 10_000
    cfg.artifact_compression_threshold_chars = 180_000
    cfg.artifact_compression_batch_chars = 30_000
    cfg.artifact_compression_output_chars = 12_000
    cfg.python_backend = "mcp_sandbox"


_INT_LIMIT_KEYS = (
    "max_steps", "max_search_calls", "max_read_calls", "max_python_calls",
    "max_site_map_calls", "extra_quota_search_calls", "extra_quota_read_calls",
)
_FLOAT_LIMIT_KEYS = ("total_timeout_sec", "synthesis_reserve_sec", "controller_timeout_sec")

_INT_CONTEXT_KEYS = (
    "max_sources", "search_results_per_call", "synthesis_context_budget",
    "read_page_max_chars", "read_chunk_chars", "read_chunk_overlap",
    "tool_observation_max_chars", "artifact_compression_threshold_chars",
    "artifact_compression_batch_chars", "artifact_compression_output_chars",
)


def _apply_limits(cfg: ResearchConfig, section: dict) -> None:
    for key in _INT_LIMIT_KEYS:
        if key in section:
            setattr(cfg, key, int(section[key]))
    for key in _FLOAT_LIMIT_KEYS:
        if key in section:
            setattr(cfg, key, float(section[key]))


def _apply_context(cfg: ResearchConfig, section: dict) -> None:
    for key in _INT_CONTEXT_KEYS:
        if key in section:
            setattr(cfg, key, int(section[key]))


def _apply_sandbox_backend(cfg: ResearchConfig, section: dict) -> None:
    if section.get("python_backend"):
        cfg.python_backend = str(section["python_backend"])


def _fill_settings(settings: OverdriveSettings, data: dict) -> None:
    sandbox = data.get("sandbox", {})
    settings.sandbox_enabled = bool(sandbox.get("enabled", True))
    for attr, key in (
        ("sandbox_image", "image"),
        ("sandbox_cpu", "cpu"),
        ("sandbox_memory", "memory"),
        ("sandbox_memory_swap", "memory_swap"),
        ("sandbox_pids_limit", "pids_limit"),
    ):
        if key in sandbox:
            setattr(settings, attr, str(sandbox[key]))

    imp = data.get("import_web_file", {})
    settings.import_file_enabled = bool(imp.get("enabled", True))
    if "max_size_mb" in imp:
        settings.import_file_max_size_mb = int(imp["max_size_mb"])
    if "timeout_sec" in imp:
        settings.import_file_timeout_sec = int(imp["timeout_sec"])
