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
from .chat_data_snapshot import (
    ChatDataSnapshot,
    ChatDataSnapshotManager,
    ChatDataSource,
    SnapshotCleanupError,
    SnapshotPayloadState,
    SnapshotSaveError,
    SnapshotStatus,
    SnapshotValidation,
)
from .dto import (
    AnalysisDiagnosticCounts,
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
    InvalidAnalysisScope,
    NoMessagesInScope,
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
from .report_history import (
    AnalysisHistoryRecord,
    ReportHistoryManager,
    ReportHistoryWriteError,
)
from .qq_connection_service import (
    QQConnectionService,
    QQConnectionStatus,
)
from .qq_export_import_service import (
    QQExportAcquisition,
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
from .scope_filter import AnalysisScope, AnalysisScopeMode

__all__ = [
    "ActivityReport",
    "AnalysisApplicationService",
    "AnalysisConfig",
    "AnalysisDiagnosticCounts",
    "AnalysisHistoryRecord",
    "AnalysisOutcome",
    "AnalysisReports",
    "AnalysisRequestDTO",
    "AnalysisResultDTO",
    "AnalysisScope",
    "AnalysisScopeMode",
    "AnalysisStatus",
    "AnalysisTask",
    "ApplicationServiceError",
    "ArtifactDTO",
    "ArtifactGenerationFailed",
    "ChatAnalyzerFacade",
    "ChatDataSnapshot",
    "ChatDataSnapshotManager",
    "ChatDataSource",
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
    "InvalidAnalysisScope",
    "MessageLengthReport",
    "NoSupportedInput",
    "NoMessagesInScope",
    "QQExportFileMissing",
    "QQExportAcquisition",
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
    "ReportHistoryManager",
    "ReportHistoryWriteError",
    "SessionInfo",
    "SourceInfo",
    "SourceUnavailable",
    "SnapshotCleanupError",
    "SnapshotPayloadState",
    "SnapshotSaveError",
    "SnapshotStatus",
    "SnapshotValidation",
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
