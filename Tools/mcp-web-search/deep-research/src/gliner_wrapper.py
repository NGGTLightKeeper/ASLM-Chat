# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from typing import Optional
from .config import GLINER_FORCE_CPU, GLINER_MODEL, GLINER_THRESHOLD, GLINER_THRESHOLD_RU

# Query label presets.
LABELS_BY_DOMAIN = {
    "general": [
        "person",
        "organization",
        "location",
        "date",
        "money",
        "product",
    ],
    "technical": [
        "company",
        "product",
        "technology",
        "programming language",
        "software",
        "hardware",
        "version",
    ],
    "finance": [
        "company",
        "revenue",
        "profit",
        "stock price",
        "market cap",
        "percentage",
        "currency",
    ],
    "academic": [
        "researcher",
        "institution",
        "method",
        "finding",
        "dataset",
        "metric",
    ],
    "medical": [
        "gene",
        "protein",
        "biomarker",
        "cancer type",
        "antibody",
        "diagnosis",
        "treatment",
        "drug",
    ],
    "journalistic": [
        "person",
        "organization",
        "location",
        "date",
        "event",
        "money",
    ],
}

# Query routing helpers.
def get_labels_for_query(
    query: str,
    query_type: Optional[str] = None,
) -> list[str]:
    """Choose GLiNER labels from the explicit or inferred query type."""

    if query_type and query_type in LABELS_BY_DOMAIN:
        return LABELS_BY_DOMAIN[query_type]

    query_lower = query.lower()
    if any(keyword in query_lower for keyword in ["api", "code", "python", "github", "library", "framework"]):
        return LABELS_BY_DOMAIN["technical"]
    if any(keyword in query_lower for keyword in ["revenue", "market", "stock", "invest", "profit"]):
        return LABELS_BY_DOMAIN["finance"]
    if any(keyword in query_lower for keyword in ["paper", "research", "study", "experiment"]):
        return LABELS_BY_DOMAIN["academic"]
    if any(keyword in query_lower for keyword in ["patient", "disease", "treatment", "clinical"]):
        return LABELS_BY_DOMAIN["medical"]

    return LABELS_BY_DOMAIN["general"]

# Model lifecycle helpers.
_model = None

# Model lifecycle helpers.
def _get_gliner_device() -> str:
    """Choose the device used for GLiNER inference."""

    if GLINER_FORCE_CPU:
        return "cpu"

    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass

    return "cpu"

# Model lifecycle helpers.
def _get_model():
    """Load and cache the GLiNER model on first use."""

    global _model

    if _model is None:
        from gliner import GLiNER

        device = _get_gliner_device()
        _model = GLiNER.from_pretrained(GLINER_MODEL)
        try:
            import torch

            _model = _model.to(torch.device(device))
        except Exception:
            pass

    return _model

# Entity extraction helpers.
def extract_entities(
    text: str,
    labels: list[str],
    threshold: float = GLINER_THRESHOLD,
    max_length: int = 3000,
) -> list[dict]:
    """Extract entities from the first part of a text with GLiNER."""

    try:
        model = _get_model()
    except Exception:
        return []

    chunk = text[:max_length]
    try:
        raw_entities = model.predict_entities(chunk, labels, threshold=threshold)
        return [
            {
                "text": entity["text"],
                "label": entity["label"],
                "score": round(entity["score"], 3),
            }
            for entity in raw_entities
        ]
    except Exception:
        return []

# Entity extraction helpers.
def check_information_density(
    text: str,
    labels: list[str],
    min_entities: int = 2,
    threshold: float = GLINER_THRESHOLD,
) -> tuple[bool, list[dict]]:
    """Return whether the text passes the minimum entity-density threshold."""

    entities = extract_entities(text, labels, threshold=threshold)
    return len(entities) >= min_entities, entities

# Entity extraction helpers.
def detect_language_and_adjust_threshold(text: str) -> float:
    """Lower the threshold for texts that likely contain Cyrillic."""

    cyrillic_count = sum(1 for char in text[:500] if "\u0400" <= char <= "\u04ff")
    if cyrillic_count > 50:
        return GLINER_THRESHOLD_RU

    return GLINER_THRESHOLD
