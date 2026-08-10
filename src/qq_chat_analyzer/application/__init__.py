"""Stable application-layer contracts for local chat analysis."""

from ..analysis.models import (
    ActivityReport,
    AnalysisReports,
    ConversationReport,
    MessageLengthReport,
    UserProfileReport,
)
from .analysis_service import AnalysisApplicationService
from .connection import (
    ConnectionSnapshot,
    ConnectionState,
    QQAuthBridge,
    QQConnectionManager,
)
from .dto import (
    AnalysisRequestDTO,
    AnalysisResultDTO,
    AnalysisStatus,
    ArtifactDTO,
    WordFrequencyDTO,
)
from .export_task_manager import (
    ExportTaskManager,
    ExportTaskState,
    ExportTaskStatus,
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
from .qq_connection_service import (
    QQConnectionService,
    QQConnectionStatus,
)
from .qq_export_import_service import (
    QQExportFileMissing,
    QQExportImportRequest,
    QQExportImportService,
    QQExportProvider,
    QQExportUnavailable,
)
from .runtime import (
    QQRuntimeManager,
    QQRuntimeState,
    QQRuntimeStatus,
)
from .wechat_export_import_service import (
    WeChatExportFileMissing,
    WeChatExportImportRequest,
    WeChatExportImportService,
    WeChatExportProvider,
    WeChatExportUnavailable,
)
from .wechat_connection_service import (
    WeChatConnectionService,
    WeChatConnectionStatus,
)
from .wechat_environment_config import (
    WeChatConfigCorrupted,
    WeChatConfigNotFound,
    WeChatConfigWriteFailed,
    WeChatEnvironmentConfig,
    WeChatEnvironmentConfigError,
    WeChatEnvironmentConfigLoader,
    WeChatEnvironmentConfigWriter,
)
from .wechat_provider_factory import (
    WeChatProviderFactory,
    WeChatProviderUnavailable,
)
from .wechat_setup_service import (
    WeChatSetupService,
    WeChatSetupState,
    WeChatSetupStatus,
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
    "ConnectionSnapshot",
    "ConnectionState",
    "ConversationReport",
    "ExportConfig",
    "ExportTaskManager",
    "ExportTaskState",
    "ExportTaskStatus",
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
    "QQRuntimeManager",
    "QQRuntimeState",
    "QQRuntimeStatus",
    "QQConnectionManager",
    "QQAuthBridge",
    "QQConnectionService",
    "QQConnectionStatus",
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
    "WeChatConnectionService",
    "WeChatConnectionStatus",
    "WeChatConfigCorrupted",
    "WeChatConfigNotFound",
    "WeChatConfigWriteFailed",
    "WeChatEnvironmentConfig",
    "WeChatEnvironmentConfigError",
    "WeChatEnvironmentConfigLoader",
    "WeChatEnvironmentConfigWriter",
    "WeChatProviderFactory",
    "WeChatProviderUnavailable",
    "WeChatSetupService",
    "WeChatSetupState",
    "WeChatSetupStatus",
    "WordFrequencyDTO",
]
