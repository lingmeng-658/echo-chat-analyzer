"""Contract tests for the stable application-layer public API."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def test_application_package_exports_analysis_application_service() -> None:
    application = importlib.import_module("qq_chat_analyzer.application")
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )

    assert hasattr(application, "AnalysisApplicationService")
    public_service = application.AnalysisApplicationService
    assert public_service is service_module.AnalysisApplicationService
    assert "AnalysisApplicationService" in application.__all__
    assert callable(public_service.execute)
