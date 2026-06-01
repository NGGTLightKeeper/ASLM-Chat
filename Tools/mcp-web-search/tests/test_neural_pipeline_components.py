# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import json
from pathlib import Path

import pytest

from conftest import requires_aslm_models
from core.cache.source_cache import SourceCache
from core.config.pipeline_modes import normalize_pipeline_mode
from core.query.aslm_embedding_runtime import (
    SearchModelSession,
    default_query_classifier_path,
    default_source_relevance_path,
    _resolve_device,
)
from core.query.routing_score import (
    QueryClassWeight,
    allocate_source_budget,
    compute_routing_score,
    ensure_general_fallback,
    normalize_class_mix,
)
import services.web_search as web_search_module


# ASLM model paths and on-disk exports.

# test_model_paths_resolve_under_models_dir — default encoder/decoder dirs share parent.

@pytest.mark.unit
def test_model_paths_resolve_under_models_dir() -> None:
    assert default_query_classifier_path().name == "aslm_embedding_encoder"
    assert default_source_relevance_path().name == "aslm_embedding_decoder"
    assert default_query_classifier_path().parent == default_source_relevance_path().parent


# test_aslm_model_exports_exist_on_disk — labels.json present under both model dirs.

@requires_aslm_models
@pytest.mark.unit
def test_aslm_model_exports_exist_on_disk() -> None:
    assert (default_query_classifier_path() / "labels.json").is_file()
    assert (default_source_relevance_path() / "labels.json").is_file()


# SearchModelSession — load flags, device resolver, and scope behavior.

# test_search_model_session_can_be_disabled_and_closed — load=False leaves encoder/decoder None.

def test_search_model_session_can_be_disabled_and_closed() -> None:
    session = SearchModelSession(load=False)
    with session as active:
        assert active.encoder is None
        assert active.decoder is None
        assert not active.ready
    assert session.encoder is None
    assert session.decoder is None


# test_search_model_session_respects_component_flags — env disables decoder while encoder loads.

def test_search_model_session_respects_component_flags(monkeypatch) -> None:
    monkeypatch.setenv("ASLM_WEB_SEARCH_NEURAL_ENCODER", "0")
    monkeypatch.setenv("ASLM_WEB_SEARCH_NEURAL_DECODER", "0")

    class _FakeRuntime:
        labels = ("general",)

        # __init__ — no-op stand-in for AslmEmbeddingRuntime.
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        # close — no-op teardown.
        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "core.query.aslm_embedding_runtime.AslmEmbeddingRuntime",
        _FakeRuntime,
    )
    session = SearchModelSession(load=True, load_encoder=True, load_decoder=False)
    with session as active:
        assert active.encoder is not None
        assert active.decoder is None
        assert active.ready


# test_model_device_resolver_is_explicit_cuda_opt_in — _resolve_device honors cpu/cuda/auto.

def test_model_device_resolver_is_explicit_cuda_opt_in(monkeypatch) -> None:
    assert _resolve_device("cpu") == "cpu"
    assert _resolve_device("cuda") in {"cpu", "cuda"}
    assert _resolve_device("auto") in {"cpu", "cuda"}
    assert _resolve_device("cuda:0") in {"cpu", "cuda"}


# Routing score and source cache — class mix, budget, registry weights, cache metadata.

# test_single_class_mix_adds_general_fallback — single-class mix gets general backfill.

def test_single_class_mix_adds_general_fallback() -> None:
    mix = ensure_general_fallback([QueryClassWeight("technical", 1.0, "model")])

    assert [item.name for item in mix] == ["technical", "general"]
    assert abs(sum(item.weight for item in mix) - 1.0) < 0.001
    assert mix[0].weight > mix[1].weight


# test_source_budget_allocation_sums_to_total — allocate_source_budget partitions max_results.

def test_source_budget_allocation_sums_to_total() -> None:
    mix = normalize_class_mix([
        QueryClassWeight("technical", 0.6),
        QueryClassWeight("academic", 0.4),
    ])
    budget = allocate_source_budget(mix, 10)

    assert sum(budget.values()) == 10
    assert budget["technical"] == 6
    assert budget["academic"] == 4


# test_routing_score_uses_registry_weights — pubmed URL gets json_api and multiplier > 1.

def test_routing_score_uses_registry_weights() -> None:
    score = compute_routing_score(
        "https://pubmed.ncbi.nlm.nih.gov/123456/",
        [QueryClassWeight("medical", 0.6), QueryClassWeight("academic", 0.4)],
    )

    assert score.multiplier > 1.0
    assert score.debug["domain_pattern"] == "pubmed.ncbi.nlm.nih.gov"
    assert score.debug["access_method"] == "json_api"


# test_source_cache_records_class_metadata — query_source_classes row stores mix and scores.

def test_source_cache_records_class_metadata(tmp_path: Path) -> None:
    cache = SourceCache(str(tmp_path / "source_cache.db"))
    cache.record_query_source_classes(
        "c++ vector erase complexity",
        "https://example.com/vector",
        class_mix_json=json.dumps({"technical": 1.0}),
        content_classes_json=json.dumps({"parsed": [["technical", 0.9]]}),
        snippet_score=0.3,
        parsed_score=0.8,
    )

    conn = cache._get_conn()
    row = conn.execute("SELECT * FROM query_source_classes").fetchone()
    assert row["class_mix_json"] == '{"technical": 1.0}'
    assert row["snippet_score"] == 0.3
    assert row["parsed_score"] == 0.8


# Pipeline mode and web_search neural flags — aliases, rules vs aslm_embedding, keep_models.

# test_pipeline_mode_aliases — legacy/neural_v2 aliases normalize to rules/aslm_embedding.

def test_pipeline_mode_aliases() -> None:
    assert normalize_pipeline_mode("legacy") == "rules"
    assert normalize_pipeline_mode("neural_v2") == "aslm_embedding"
    assert normalize_pipeline_mode("rules") == "rules"
    assert normalize_pipeline_mode(None) == "rules"


# test_pipeline_rules_disables_neural_stack — pipeline env and encoder flag gate _use_neural_pipeline.

def test_pipeline_rules_disables_neural_stack(monkeypatch) -> None:
    monkeypatch.delenv("ASLM_WEB_SEARCH_NEURAL_ENCODER", raising=False)
    monkeypatch.delenv("ASLM_WEB_SEARCH_NEURAL_DECODER", raising=False)
    monkeypatch.setenv("ASLM_WEB_SEARCH_PIPELINE", "rules")

    assert web_search_module._pipeline_mode() == "rules"
    assert not web_search_module._use_neural_pipeline("high")

    monkeypatch.setenv("ASLM_WEB_SEARCH_PIPELINE", "legacy")
    assert web_search_module._pipeline_mode() == "rules"
    assert not web_search_module._use_neural_pipeline("high")

    monkeypatch.setenv("ASLM_WEB_SEARCH_PIPELINE", "aslm_embedding")
    assert not web_search_module._use_neural_pipeline("high")
    assert not web_search_module._use_neural_pipeline("medium")

    monkeypatch.setenv("ASLM_WEB_SEARCH_NEURAL_ENCODER", "1")
    assert web_search_module._neural_encoder_enabled("high")
    assert not web_search_module._neural_decoder_enabled("high")
    assert web_search_module._use_neural_pipeline("high")

    monkeypatch.setenv("ASLM_WEB_SEARCH_PIPELINE", "neural_v2")
    assert web_search_module._pipeline_mode() == "aslm_embedding"
    assert web_search_module._neural_encoder_enabled("high")


# test_keep_models_loaded_env_defaults_to_disabled — ASLM_WEB_SEARCH_KEEP_MODELS parsing.

def test_keep_models_loaded_env_defaults_to_disabled(monkeypatch) -> None:
    monkeypatch.delenv("ASLM_WEB_SEARCH_KEEP_MODELS", raising=False)
    assert not web_search_module._keep_search_models_loaded()

    monkeypatch.setenv("ASLM_WEB_SEARCH_KEEP_MODELS", "0")
    assert not web_search_module._keep_search_models_loaded()

    monkeypatch.setenv("ASLM_WEB_SEARCH_KEEP_MODELS", "false")
    assert not web_search_module._keep_search_models_loaded()

    monkeypatch.setenv("ASLM_WEB_SEARCH_KEEP_MODELS", "1")
    assert web_search_module._keep_search_models_loaded()


# test_search_model_device_env_overrides_config — ASLM_WEB_SEARCH_MODEL_DEVICE env wins.

def test_search_model_device_env_overrides_config(monkeypatch) -> None:
    monkeypatch.setenv("ASLM_WEB_SEARCH_MODEL_DEVICE", "cuda")
    assert web_search_module._search_model_device() == "cuda"

    monkeypatch.setenv("ASLM_WEB_SEARCH_MODEL_DEVICE", "cpu")
    assert web_search_module._search_model_device() == "cpu"


# Shared SearchModelSession — scope clears session when keep_models off; reuse when on.

# test_search_model_session_scope_clears_shared_when_neural_off — medium effort with keep_models=0 skips load.

def test_search_model_session_scope_clears_shared_when_neural_off(monkeypatch) -> None:
    monkeypatch.setenv("ASLM_WEB_SEARCH_PIPELINE", "aslm_embedding")
    monkeypatch.setenv("ASLM_WEB_SEARCH_NEURAL_ENCODER", "1")
    monkeypatch.setenv("ASLM_WEB_SEARCH_NEURAL_DECODER", "1")
    monkeypatch.setenv("ASLM_WEB_SEARCH_KEEP_MODELS", "1")

    class FakeSession:
        # __init__ — record kwargs and load flag from factory.
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.load = bool(kwargs.get("load", True))
            self.closed = False

        # __enter__ — context manager entry.
        def __enter__(self):
            return self

        # __exit__ — context manager exit.
        def __exit__(self, *args) -> None:
            return None

        # close — mark session closed.
        def close(self) -> None:
            self.closed = True

        # ready — True when load was requested.
        @property
        def ready(self) -> bool:
            return self.load

    created: list[FakeSession] = []

    # factory — build FakeSession and track instances.
    def factory(**kwargs):
        session = FakeSession(**kwargs)
        created.append(session)
        return session

    monkeypatch.setattr(web_search_module, "SearchModelSession", factory)
    web_search_module.clear_shared_search_model_session()

    with web_search_module._search_model_session_scope("high") as session:
        assert session.ready

    monkeypatch.setenv("ASLM_WEB_SEARCH_KEEP_MODELS", "0")
    with web_search_module._search_model_session_scope("medium") as session:
        assert not session.ready
    assert created[-1].kwargs.get("load") is False


# test_shared_model_session_reuses_loaded_session — same FakeSession instance on second get.

def test_shared_model_session_reuses_loaded_session(monkeypatch) -> None:
    web_search_module.clear_shared_search_model_session()
    created: list[object] = []

    class FakeSession:
        # __init__ — track load/encoder/decoder flags for reuse test.
        def __init__(
            self,
            *,
            load: bool = True,
            device: str = "cpu",
            load_encoder: bool | None = None,
            load_decoder: bool | None = None,
        ) -> None:
            self.load = load
            self.device = device
            self.load_encoder = bool(load_encoder)
            self.load_decoder = bool(load_decoder)
            self.encoder = None
            self.decoder = None
            self.closed = False
            created.append(self)

        # __enter__ — attach encoder/decoder stubs when flags set.
        def __enter__(self):
            if self.load_encoder:
                self.encoder = object()
            if self.load_decoder:
                self.decoder = object()
            return self

        # close — clear stubs and mark closed.
        def close(self) -> None:
            self.closed = True
            self.encoder = None
            self.decoder = None

        # ready — True when either encoder or decoder loaded.
        @property
        def ready(self) -> bool:
            return self.encoder is not None or self.decoder is not None

    monkeypatch.setattr(web_search_module, "SearchModelSession", FakeSession)

    first = web_search_module._get_shared_search_model_session(
        "high", load_encoder=True, load_decoder=False
    )
    second = web_search_module._get_shared_search_model_session(
        "high", load_encoder=True, load_decoder=False
    )

    assert first is second
    assert len(created) == 1

    web_search_module.clear_shared_search_model_session()
    assert first.closed
