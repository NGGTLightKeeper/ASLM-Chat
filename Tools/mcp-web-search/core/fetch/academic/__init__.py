# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from .engine import AcademicSearchEngine, search_academic
from .models import AcademicPaper, AcademicProviderAttempt, AcademicSearchResult

__all__ = [
    "AcademicPaper",
    "AcademicProviderAttempt",
    "AcademicSearchEngine",
    "AcademicSearchResult",
    "search_academic",
]
