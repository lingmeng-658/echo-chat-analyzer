"""Stable application-layer contracts for local chat analysis."""

from ..analysis.models import (
    ActivityReport,
    AnalysisReports,
    ConversationReport,
    MessageLengthReport,
    UserProfileReport,
)
from .analysis_service import AnalysisApplicationService
from .dto import (
    AnalysisRequestDTO,
    AnalysisResultDTO,
    AnalysisStatus,
    ArtifactDTO,
    WordFrequencyDTO,
)
from .export_config import ExportConfig
from .errors import (
    ApplicationServiceError,
    ArtifactGenerationFailed,
    InputPathNotFound,
    InvalidAnalysisRequest,
    NoSupportedInput,
)
from .facade import (
    AnalysisConfig,
    AnalysisOutcome,
    ChatAnalyzerFacade,
    ChatSource,
    FacadeError,
    SessionInfo,
    SourceInfo,
    SourceUnavailable,
    UnknownChatSource,
)
from .import_outcome import ImportOutcome
from .import_request import ImportRequest
from .import_result import ImportResult
from .import_service import ImportService
from .qq_export_import_service import (
    QQExportFileMissing,
    QQExportImportRequest,
    QQExportImportService,
    QQExportProvider,
    QQExportUnavailable,
)
from .wechat_export_import_service import (
    WeChatExportFileMissing,
    WeChatExportImportRequest,
    WeChatExportImportService,
    WeChatExportProvider,
    WeChatExportUnavailable,
)
from .task import AnalysisTask

__all__ = [
    "ActivityReport",
    "AnalysisApplicationService",
    "AnalysisConfig",
    "AnalysisOutcome",
    "AnalysisReports",
    "AnalysisRequestDTO",
    "AnalysisResultDTO",
    "AnalysisStatus",
    "AnalysisTask",
    "ApplicationServiceError",
    "ArtifactDTO",
    "ArtifactGenerationFailed",
    "ChatAnalyzerFacade",
    "ChatSource",
    "ConversationReport",
    "ExportConfig",
    "FacadeError",
    "ImportOutcome",
    "ImportRequest",
    "ImportResult",
    "ImportService",
    "InputPathNotFound",
    "InvalidAnalysisRequest",
    "MessageLengthReport",
    "NoSupportedInput",
    "QQExportFileMissing",
    "QQExportImportRequest",
    "QQExportImportService",
    "QQExportProvider",
    "QQExportUnavailable",
    "SessionInfo",
    "SourceInfo",
    "SourceUnavailable",
    "UnknownChatSource",
    "UserProfileReport",
    "WeChatExportFileMissing",
    "WeChatExportImportRequest",
    "WeChatExportImportService",
    "WeChatExportProvider",
    "WeChatExportUnavailable",
    "WordFrequencyDTO",
]