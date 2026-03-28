# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError


# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "deep_think_config.json"


# Config models

# LLM settings
class LLMConfig(BaseModel):
    base_url: str = "http://localhost:1234/v1/chat/completions"
    model: str = "local-model"
    max_concurrent_requests: int = 2
    timeout_seconds: float = 120.0
    selector_enabled: bool = True
    selector_temperature: float = 0.2
    selector_max_tokens: int = 500
    synthesis_temperature: float = 0.25
    synthesis_max_tokens: int = 2200


# Search settings
class SearchConfig(BaseModel):
    language: str = "en-US"
    results_limit: int = 5
    cache_ttl_seconds: int = 300
    max_concurrent_requests: int = 3
    enable_lightweight_read: bool = True
    lightweight_read_top_results: int = 1
    lightweight_read_char_budget: int = 2000
    overdrive: bool = False
    overdrive_human_behavior: bool = True
    overdrive_ocr_fallback: bool = True
    overdrive_parallel_timeout: float = 20.0
    overdrive_ocr_timeout: float = 30.0
    overdrive_browser_start_delay: float = 0.75
    overdrive_browser_concurrency: int = 2


# Sandbox settings
class SandboxConfig(BaseModel):
    enabled: bool = True
    timeout_seconds: int = 20
    auto_confirm: bool = True
    max_output_chars: int = 12000
    container_name: str = "deep-think-sandbox"
    image: str = "deep-think-sandbox:latest"
    image_source: str = "local"


# Runtime limits
class LimitsConfig(BaseModel):
    max_active_agents: int = 4
    max_iterations_per_agent: int = 4
    task_timeout_seconds: float = 600.0
    per_agent_timeout_seconds: float = 240.0
    max_reflect_without_tool: int = 2


# Output settings
class OutputConfig(BaseModel):
    root_dir: str = "_out"
    write_events_jsonl: bool = True
    write_markdown: bool = True
    write_json: bool = True


# MCP defaults
class MCPConfig(BaseModel):
    default_profile: str = "balanced"
    include_raw_reports_in_full: bool = True


# Profile overrides
class ProfileConfig(BaseModel):
    max_active_agents: int | None = None
    max_iterations_per_agent: int | None = None
    search_results_limit: int | None = None
    sandbox_timeout_seconds: int | None = None
    synthesis_max_tokens: int | None = None
    per_agent_timeout_seconds: float | None = None


# Per-agent runtime overrides
class AgentRuntimeConfig(BaseModel):
    enabled: bool = True
    has_search: bool = False
    has_python: bool = False
    temperature: float = 0.3
    max_tokens: int = 1800


# Root settings model
class Settings(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)
    agents: dict[str, AgentRuntimeConfig] = Field(default_factory=dict)
    output: OutputConfig = Field(default_factory=OutputConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    config_path: Path = DEFAULT_CONFIG_PATH

    @property
    def output_root(self) -> Path:
        """Resolve the output directory used for task artifacts."""

        root_dir = self.output.root_dir
        path = Path(root_dir)
        if path.is_absolute():
            return path

        # Keep the default output under the shared task workspace.
        if root_dir == "_out":
            return WORKSPACE_ROOT / "task" / "deep-think"

        return PROJECT_ROOT / root_dir

    def get_profile(self, profile_name: str | None) -> ProfileConfig:
        """Return the requested profile or the configured default profile."""

        if profile_name and profile_name in self.profiles:
            return self.profiles[profile_name]
        return self.profiles.get(self.mcp.default_profile, ProfileConfig())

    def agent_runtime(self, agent_id: str) -> AgentRuntimeConfig:
        """Return runtime overrides for a specific agent id."""

        return self.agents.get(agent_id, AgentRuntimeConfig())


    # Compatibility aliases
    @property
    def lm_studio_url(self) -> str:
        """Return the configured LM Studio endpoint."""

        return self.llm.base_url

    @property
    def lm_studio_model(self) -> str:
        """Return the configured LM Studio model id."""

        return self.llm.model

    @property
    def max_concurrent_llm_requests(self) -> int:
        """Return the LLM concurrency limit."""

        return self.llm.max_concurrent_requests

    @property
    def llm_timeout_seconds(self) -> float:
        """Return the LLM request timeout."""

        return self.llm.timeout_seconds

    @property
    def searxng_language(self) -> str:
        """Return the default search language."""

        return self.search.language

    @property
    def search_results_limit(self) -> int:
        """Return the default search result count."""

        return self.search.results_limit

    @property
    def search_cache_ttl_seconds(self) -> int:
        """Return the search cache TTL in seconds."""

        return self.search.cache_ttl_seconds

    @property
    def max_concurrent_search_requests(self) -> int:
        """Return the search concurrency limit."""

        return self.search.max_concurrent_requests

    @property
    def max_active_agents(self) -> int:
        """Return the maximum number of active agents."""

        return self.limits.max_active_agents

    @property
    def max_search_steps_per_agent(self) -> int:
        """Return the default iteration limit per agent."""

        return self.limits.max_iterations_per_agent

    @property
    def task_timeout_seconds(self) -> float:
        """Return the overall task timeout."""

        return self.limits.task_timeout_seconds


# Environment overrides
# ASLM injects settings as ASLM_<KEY> environment variables at module startup.
# lms_url arrives as "host:port", so we normalize it to a full chat completions URL.
def _aslm_lms_url() -> str | None:
    raw = os.getenv("ASLM_LMS_URL")
    if raw is None:
        return None
    url = raw if raw.startswith("http") else f"http://{raw}"
    return url.rstrip("/") + "/v1/chat/completions"


_ENV_OVERRIDES: dict[str, tuple[str, ...]] = {
    # ASLM native vars (populated automatically by the launcher).
    "DEEP_THINK_LM_STUDIO_URL": ("llm", "base_url"),
    "DEEP_THINK_LM_STUDIO_MODEL": ("llm", "model"),
    "DEEP_THINK_LLM_TIMEOUT_SECONDS": ("llm", "timeout_seconds"),
    "DEEP_THINK_MAX_CONCURRENT_LLM_REQUESTS": ("llm", "max_concurrent_requests"),
    "DEEP_THINK_SEARXNG_LANGUAGE": ("search", "language"),
    "DEEP_THINK_SEARCH_RESULTS_LIMIT": ("search", "results_limit"),
    "DEEP_THINK_SEARCH_CACHE_TTL_SECONDS": ("search", "cache_ttl_seconds"),
    "DEEP_THINK_MAX_CONCURRENT_SEARCH_REQUESTS": ("search", "max_concurrent_requests"),
    "DEEP_THINK_MAX_ACTIVE_AGENTS": ("limits", "max_active_agents"),
    "DEEP_THINK_MAX_SEARCH_STEPS_PER_AGENT": ("limits", "max_iterations_per_agent"),
    "DEEP_THINK_TASK_TIMEOUT_SECONDS": ("limits", "task_timeout_seconds"),
    "DEEP_THINK_SANDBOX_CONTAINER": ("sandbox", "container_name"),
    "DEEP_THINK_SANDBOX_IMAGE": ("sandbox", "image"),
    "DEEP_THINK_SANDBOX_IMAGE_SOURCE": ("sandbox", "image_source"),
    # Overdrive mode overrides (also respond to SEARCH_OVERDRIVE_* vars).
    "SEARCH_OVERDRIVE": ("search", "overdrive"),
    "SEARCH_OVERDRIVE_HUMAN_BEHAVIOR": ("search", "overdrive_human_behavior"),
    "SEARCH_OVERDRIVE_OCR_FALLBACK": ("search", "overdrive_ocr_fallback"),
    "SEARCH_OVERDRIVE_PARALLEL_TIMEOUT": ("search", "overdrive_parallel_timeout"),
    "SEARCH_OVERDRIVE_OCR_TIMEOUT": ("search", "overdrive_ocr_timeout"),
    "SEARCH_OVERDRIVE_BROWSER_START_DELAY": ("search", "overdrive_browser_start_delay"),
    "SEARCH_OVERDRIVE_BROWSER_CONCURRENCY": ("search", "overdrive_browser_concurrency"),
}


# Config merge helpers

# Recursively merge override dictionaries into a base dictionary
def _deep_update(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge nested dictionaries without mutating the input."""

    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_update(merged[key], value)
        else:
            merged[key] = value
    return merged

def _coerce_env_value(raw: str) -> Any:
    """Coerce environment override values into bools, numbers, or strings."""

    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"

    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw

def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply environment overrides onto the loaded config payload."""

    updated = deepcopy(data)

    # Apply ASLM_LMS_URL first so DEEP_THINK_LM_STUDIO_URL can still override it.
    aslm_url = _aslm_lms_url()
    if aslm_url is not None:
        updated.setdefault("llm", {})["base_url"] = aslm_url

    for env_name, path in _ENV_OVERRIDES.items():
        raw = os.getenv(env_name)
        if raw is None:
            continue

        target = updated
        for key in path[:-1]:
            target = target.setdefault(key, {})
        target[path[-1]] = _coerce_env_value(raw)

    return updated


# Config loading

# Build the default config payload from model defaults
def _default_config_payload() -> dict[str, Any]:
    """Return the default configuration payload without runtime-only fields."""

    return Settings().model_dump(exclude={"config_path"})

def _load_raw_config(path: Path) -> dict[str, Any]:
    """Load the raw JSON config file and merge it with defaults."""

    if not path.exists():
        return _default_config_payload()

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError(f"Deep Think config must be a JSON object: {path}")

    return _deep_update(_default_config_payload(), payload)

def load_settings(config_path: Path | None = None) -> Settings:
    """Load, validate, and return runtime settings."""

    path = config_path or DEFAULT_CONFIG_PATH
    raw = _load_raw_config(path)
    raw = _apply_env_overrides(raw)

    try:
        loaded_settings = Settings.model_validate({**raw, "config_path": path})
    except ValidationError as exc:
        raise RuntimeError(f"Invalid Deep Think config at {path}: {exc}") from exc

    return loaded_settings


settings = load_settings()
