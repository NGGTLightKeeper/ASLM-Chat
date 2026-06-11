# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from core.config.settings import load_search_config
from services.web_search import _build_effort_options, _effort_hard_timeout


def test_default_config_uses_stability_profile() -> None:
    assert load_search_config().search.routing_profile == "stability"


def test_low_effort_forces_stability_profile() -> None:
    cfg = load_search_config()

    options = _build_effort_options(
        cfg,
        effort="low",
        max_results=5,
        fetch_previews=True,
        timelimit=None,
    )

    assert options.routing_profile == "stability"


def test_medium_uses_stability_and_high_uses_quality_profile() -> None:
    cfg = load_search_config()

    medium = _build_effort_options(cfg, effort="medium", max_results=5, fetch_previews=True, timelimit=None)
    high = _build_effort_options(cfg, effort="high", max_results=5, fetch_previews=True, timelimit=None)

    assert medium.routing_profile == "stability"
    assert high.routing_profile == "quality"


def test_medium_hard_timeout_is_not_expanded_for_quality() -> None:
    cfg = load_search_config()

    assert _effort_hard_timeout("medium", None) < cfg.search.quality_hard_timeout
