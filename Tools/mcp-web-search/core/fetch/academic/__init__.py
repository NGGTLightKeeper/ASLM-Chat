# Copyright NEXTGGTECH. Elastic License 2.0.

from .engine import AcademicSearchEngine, search_academic
from .models import AcademicPaper, AcademicProviderAttempt, AcademicSearchResult

__all__ = [
    "AcademicPaper",
    "AcademicProviderAttempt",
    "AcademicSearchEngine",
    "AcademicSearchResult",
    "search_academic",
]
