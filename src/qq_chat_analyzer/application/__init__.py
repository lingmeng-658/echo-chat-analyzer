"""Stable application-layer contracts for local chat analysis."""

from .dto import (
    AnalysisRequestDTO,
    AnalysisResultDTO,
    AnalysisStatus,
    ArtifactDTO,
    WordFrequencyDTO,
)
from .errors import (
    ApplicationServiceError,
    ArtifactGenerationFailed,
    InputPathNotFound,
    InvalidAnalysisRequest,
    NoSupportedInput,
)

__all__ = [
    "AnalysisRequestDTO",
    "AnalysisResultDTO",
    "AnalysisStatus",
    "ApplicationServiceError",
    "ArtifactDTO",
    "ArtifactGenerationFailed",
    "InputPathNotFound",
    "InvalidAnalysisRequest",
    "NoSupportedInput",
    "WordFrequencyDTO",
]
