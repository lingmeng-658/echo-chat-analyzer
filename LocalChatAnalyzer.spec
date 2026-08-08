# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build definition for the Local Chat Analyzer desktop app.

Build with:
    .\.venv\Scripts\pyinstaller.exe LocalChatAnalyzer.spec

Output: dist/LocalChatAnalyzer.exe
"""

from pathlib import Path


project_root = Path(SPEC).resolve().parent
resources = (
    project_root / "stopwords.txt",
    project_root / "stopwords_topic.txt",
    project_root / "stopwords_culture.txt",
)
datas = [(str(path), ".") for path in resources]


a = Analysis(
    ["desktop_entry.py"],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LocalChatAnalyzer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
