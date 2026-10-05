"""Keep default user-data paths inside each automated test's sandbox."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_user_data(tmp_path, monkeypatch):
    home = tmp_path / "test-home"
    for variable, directory in {
        "LOCALAPPDATA": tmp_path / "local-app-data",
        "APPDATA": tmp_path / "roaming-app-data",
        "USERPROFILE": home,
        "HOME": home,
        "XDG_DATA_HOME": tmp_path / "xdg-data",
        "XDG_CONFIG_HOME": tmp_path / "xdg-config",
        "XDG_CACHE_HOME": tmp_path / "xdg-cache",
    }.items():
        monkeypatch.setenv(variable, str(directory))
    # Cover home fallback and providers using Path.home(), including tests
    # that remove LOCALAPPDATA. Individual tests can still override this.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))


@pytest.fixture(scope="function")
def qq_asset_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Point the QQ resolver at a throwaway directory of fake PNGs."""
    from qq_chat_analyzer.presentation import expression_assets

    root = tmp_path / "qq-emojis"
    root.mkdir()
    monkeypatch.setattr(
        expression_assets, "QQ_ASSET_ROOT", str(root), raising=False
    )
    monkeypatch.setattr(
        expression_assets, "_qq_asset_index", None, raising=False
    )
    return root
