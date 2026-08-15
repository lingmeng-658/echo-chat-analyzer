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
echo_icon = project_root / "assets/branding/echo/echo_icon.ico"
windows_exe_icon = project_root / "branding/Echo.ico"
echo_favicon = project_root / "assets/branding/echo/echo_icon_32.png"
echo_report_logo = project_root / "assets/branding/echo/echo_wordmark_with_slogan.png"
echo_expression_assets = project_root / "frontend/echo_report/wechat-emojis"
datas = [(str(path), ".") for path in resources]
datas.append((str(echo_icon), "assets/branding/echo"))
datas.append((str(echo_favicon), "assets/branding/echo"))
datas.append((str(echo_report_logo), "assets/branding/echo"))
datas.append((str(echo_expression_assets), "frontend/echo_report/wechat-emojis"))


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
    icon=str(windows_exe_icon),
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
