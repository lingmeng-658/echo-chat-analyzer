param(
    [string]$ProjectRootOverride = "",
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

$RequiredRuntimePaths = @(
    "qq\qce-server.exe",
    "qq\napcat.mjs",
    "qq\static\qce",
    "wechat\wcdb_cli.exe",
    "wechat\WCDB.dll",
    "wechat\wx_key.dll",
    "wechat\wx_key_helper.cjs",
    "wechat\node_modules\koffi\index.js"
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

    # Never publish machine-specific NapCat state, account config, or logs.
    foreach ($GeneratedName in @("cache", "config", "logs")) {
        $GeneratedPath = Join-Path $PortableRuntime "qq\$GeneratedName"
        if (Test-Path -LiteralPath $GeneratedPath) {
            Remove-Item -LiteralPath $GeneratedPath -Recurse -Force
        }
    }

    foreach ($RelativePath in $RequiredRuntimePaths) {
        $CopiedPath = Join-Path $PortableRuntime $RelativePath
        if (-not (Test-Path -LiteralPath $CopiedPath)) {
            throw "Portable runtime copy is incomplete: runtime\$RelativePath"
        }
    }

    Write-Output "Build complete: $PortableDirectory"
}
finally {
    Pop-Location
}
