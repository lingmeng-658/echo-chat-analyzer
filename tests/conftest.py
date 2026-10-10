"""Keep default user-data paths inside each automated test's sandbox."""

from pathlib import Path
import sys

import pytest


@pytest.fixture(autouse=True)
def release_test_widgets():
    """Delete this test's Qt roots while QApplication is still alive."""
    # Do not import or initialize Qt for tests that do not use it.
    widgets = sys.modules.get("PySide6.QtWidgets")
    if widgets is None:
        yield
        return

    application_type = widgets.QApplication
    if not isinstance(application_type, type):
        yield
        return

    app = application_type.instance()
    existing = set(app.allWidgets()) if isinstance(app, application_type) else set()
    yield

    app = application_type.instance()
    if not isinstance(app, application_type):
        return

    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import isValid

    # Higher-scope fixtures have already been set up; preserve their widgets,
    # including pre-existing children that a test may have reparented.
    roots = [widget for widget in app.allWidgets()
             if widget not in existing and widget.parentWidget() is None
             and not any(child in existing
                         for child in widget.findChildren(widgets.QWidget))]
    for widget in roots:
        if isValid(widget):
            widget.deleteLater()
    for widget in roots:
        if isValid(widget):
            # Target only our roots: do not drain timers or another fixture's
            # pending DeferredDelete events. Parent deletion owns its children.
            QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


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
