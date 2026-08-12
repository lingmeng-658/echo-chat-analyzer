# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build definition for the Local Chat Analyzer desktop app.

Build with:
    python -m PyInstaller LocalChatAnalyzer.spec

Output: dist/Echo/Echo.exe
"""

from pathlib import Path


project_root = Path(SPEC).resolve().parent
resources = (
    project_root / "stopwords.txt",
    project_root / "stopwords_topic.txt",
    project_root / "stopwords_culture.txt",
    project_root / "wechat_login_guide.png",
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
    [],
    exclude_binaries=True,
    name="Echo",
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

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Echo",
)
