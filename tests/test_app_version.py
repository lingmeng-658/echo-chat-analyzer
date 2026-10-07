"""Release version consumers must agree with the project metadata."""

from pathlib import Path
import importlib.metadata
import runpy
import tomllib

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _spec_datas(project_root):
    class AnalysisReached(Exception):
        pass

    captured = []

    def capture_analysis(*args, **kwargs):
        captured.extend(kwargs["datas"])
        raise AnalysisReached

    try:
        runpy.run_path(str(ROOT / "LocalChatAnalyzer.spec"), init_globals={
            "SPEC": str(project_root / "LocalChatAnalyzer.spec"),
            "Analysis": capture_analysis,
        })
    except AnalysisReached:
        pass
    return captured


def test_desktop_startup_version_matches_release_version():
    from qq_chat_analyzer.gui.app import APP_VERSION

    project = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert APP_VERSION == project["project"]["version"]


@pytest.mark.slow_integration
def test_desktop_spec_ships_release_metadata_for_runtime_version():
    datas = _spec_datas(ROOT)
    metadata_dirs = [Path(source) for source, target in datas if target.endswith(".dist-info")]
    distributions = [
        importlib.metadata.PathDistribution(path) for path in metadata_dirs
        if importlib.metadata.PathDistribution(path).metadata["Name"] == "qq-chat-analyzer"
    ]
    assert len(distributions) == 1
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert distributions[0].version == project["project"]["version"]


@pytest.mark.slow_integration
def test_desktop_build_rejects_stale_installed_release_metadata(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "99.0.0"\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="version"):
        _spec_datas(tmp_path)
