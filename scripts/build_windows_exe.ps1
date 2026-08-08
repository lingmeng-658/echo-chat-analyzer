$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PyInstaller = Join-Path $ProjectRoot ".venv\Scripts\pyinstaller.exe"

if (-not (Test-Path -LiteralPath $PyInstaller)) {
    & $VenvPython -m pip install pyinstaller
}

Push-Location $ProjectRoot
try {
    & $PyInstaller --clean --noconfirm LocalChatAnalyzer.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed with exit code $LASTEXITCODE"
    }
    Write-Output "Build complete: $ProjectRoot\dist\LocalChatAnalyzer.exe"
}
finally {
    Pop-Location
}
