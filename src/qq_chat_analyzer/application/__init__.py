"""Stable application-layer contracts for local chat analysis."""

from .analysis_service import AnalysisApplicationService
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
    "AnalysisApplicationService",
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
