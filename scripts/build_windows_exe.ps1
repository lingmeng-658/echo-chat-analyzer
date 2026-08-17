param(
    [string]$ProjectRootOverride = "",
    [string]$MsvcRuntimeDirectoryOverride = "",
    [switch]$RuntimeOnly
)

$ErrorActionPreference = "Stop"

$ProjectRoot = if ($ProjectRootOverride) {
    [System.IO.Path]::GetFullPath($ProjectRootOverride)
}
else {
    Split-Path -Parent $PSScriptRoot
}
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PyInstaller = Join-Path $ProjectRoot ".venv\Scripts\pyinstaller.exe"
$RuntimeSource = Join-Path $ProjectRoot "runtime"
$PortableDirectory = Join-Path $ProjectRoot "dist\Echo"
$PortableRuntime = Join-Path $PortableDirectory "runtime"
$MsvcRuntimeNames = @(
    "msvcp140.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll"
)
$MsvcRuntimeTargets = @("qq", "wechat")
$MsvcRuntimeMinimumVersion = [Version]"14.43"

$RequiredRuntimePaths = @(
    "qq\qce-server.exe",
    "qq\napcat.mjs",
    "qq\NapCatWinBootMain.exe",
    "qq\NapCatWinBootHook.dll",
    "qq\config\plugins.json",
    "qq\static\qce",
    "wechat\wcdb_cli.exe",
    "wechat\WCDB.dll",
    "wechat\wx_key.dll",
    "wechat\wx_key_helper.cjs",
    "wechat\node.exe",
    "wechat\node_modules\koffi\index.js",
    "wechat\node_modules\koffi\build\koffi\win32_x64\koffi.node"
)

if (-not (Test-Path -LiteralPath $RuntimeSource -PathType Container)) {
    throw "Runtime source directory is missing. Restore the repository runtime directory before building."
}

foreach ($RelativePath in $RequiredRuntimePaths) {
    $SourcePath = Join-Path $RuntimeSource $RelativePath
    if (-not (Test-Path -LiteralPath $SourcePath)) {
        throw "Required runtime resource is missing: runtime\$RelativePath"
    }
}

Push-Location $ProjectRoot
try {
    if (-not $RuntimeOnly) {
        if (-not (Test-Path -LiteralPath $PyInstaller)) {
            & $VenvPython -m pip install pyinstaller
        }
        & $PyInstaller --clean --noconfirm LocalChatAnalyzer.spec
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller build failed with exit code $LASTEXITCODE"
        }
    }

    New-Item -ItemType Directory -Force -Path $PortableDirectory | Out-Null
    if (Test-Path -LiteralPath $PortableRuntime) {
        Remove-Item -LiteralPath $PortableRuntime -Recurse -Force
    }
    Copy-Item -LiteralPath $RuntimeSource -Destination $PortableRuntime -Recurse

    # The QQ launchers and WeChat native libraries use the MSVC dynamic
    # runtime. Ship it app-local so both child-process trees also start on
    # clean Windows systems without a separately installed redistributable.
    $WindowsSystemDirectory = if ($MsvcRuntimeDirectoryOverride) {
        [System.IO.Path]::GetFullPath($MsvcRuntimeDirectoryOverride)
    }
    else {
        [Environment]::GetFolderPath("System")
    }
    foreach ($RuntimeName in $MsvcRuntimeNames) {
        $RuntimeDependency = Join-Path $WindowsSystemDirectory $RuntimeName
        if (-not (Test-Path -LiteralPath $RuntimeDependency -PathType Leaf)) {
            throw "Required native runtime dependency is missing: $RuntimeName"
        }
        $RuntimeVersionText = (
            Get-Item -LiteralPath $RuntimeDependency
        ).VersionInfo.FileVersion
        $RuntimeVersion = $null
        if (-not [Version]::TryParse($RuntimeVersionText, [ref]$RuntimeVersion)) {
            throw "Cannot determine native runtime version: $RuntimeName"
        }
        if ($RuntimeVersion -lt $MsvcRuntimeMinimumVersion) {
            throw "Native runtime dependency is too old: $RuntimeName"
        }
        foreach ($RuntimeTarget in $MsvcRuntimeTargets) {
            Copy-Item -LiteralPath $RuntimeDependency -Destination (
                Join-Path $PortableRuntime "$RuntimeTarget\$RuntimeName"
            ) -Force
        }
    }

    # Never publish machine-specific NapCat state, account config, or logs.
    foreach ($GeneratedName in @("cache", "config", "logs")) {
        $GeneratedPath = Join-Path $PortableRuntime "qq\$GeneratedName"
        if (Test-Path -LiteralPath $GeneratedPath) {
            Remove-Item -LiteralPath $GeneratedPath -Recurse -Force
        }
    }

    # Restore only the machine-independent plugin enablement seed. Account,
    # protocol, WebUI, cache, and log state remain excluded from Portable.
    $QQPluginConfigSource = Join-Path $RuntimeSource "qq\config\plugins.json"
    $QQPluginConfigDestination = Join-Path $PortableRuntime "qq\config\plugins.json"
    New-Item -ItemType Directory -Force -Path (
        Split-Path -Parent $QQPluginConfigDestination
    ) | Out-Null
    Copy-Item -LiteralPath $QQPluginConfigSource -Destination $QQPluginConfigDestination

    foreach ($RelativePath in $RequiredRuntimePaths) {
        $CopiedPath = Join-Path $PortableRuntime $RelativePath
        if (-not (Test-Path -LiteralPath $CopiedPath)) {
            throw "Portable runtime copy is incomplete: runtime\$RelativePath"
        }
    }
    foreach ($RuntimeName in $MsvcRuntimeNames) {
        foreach ($RuntimeTarget in $MsvcRuntimeTargets) {
            $CopiedDependency = Join-Path (
                $PortableRuntime
            ) "$RuntimeTarget\$RuntimeName"
            if (-not (Test-Path -LiteralPath $CopiedDependency -PathType Leaf)) {
                throw "Portable runtime copy is incomplete: runtime\$RuntimeTarget\$RuntimeName"
            }
        }
    }

    # Ship the WeChat WCDB diagnostic runner so test machines do not have to
    # copy it manually. The frozen app looks for scripts/run_wechat_wcdb_diagnostic.ps1.
    $DiagnosticRunnerSource = Join-Path $ProjectRoot "scripts\run_wechat_wcdb_diagnostic.ps1"
    if (-not (Test-Path -LiteralPath $DiagnosticRunnerSource)) {
        throw "Required diagnostic runner is missing: scripts\run_wechat_wcdb_diagnostic.ps1"
    }
    $PortableScripts = Join-Path $PortableDirectory "scripts"
    New-Item -ItemType Directory -Force -Path $PortableScripts | Out-Null
    Copy-Item -LiteralPath $DiagnosticRunnerSource -Destination (
        Join-Path $PortableScripts "run_wechat_wcdb_diagnostic.ps1"
    )

    Write-Output "Build complete: $PortableDirectory"
}
finally {
    Pop-Location
}
