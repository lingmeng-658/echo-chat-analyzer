<#
.SYNOPSIS
    从官方 Tencent/wcdb v2.1.15 源码构建微信原生依赖并同步运行产物。

.DESCRIPTION
    面向 clean clone 环境：将 Tencent/wcdb tag v2.1.15（recursive，含子模块）下载到
    gitignored 的 build/cache 区域，校验 sqlcipher/zstd 子模块固定 commit，使用
    VS2022 x64 Release (BUILD_SHARED_LIBS=ON, WCDB_ZSTD=ON) 构建官方
    WCDB.dll/WCDB.lib，再通过参数化 CMakeLists 构建 wcdb_cli，最后把 WCDB.dll 与
    wcdb_cli.exe 同步到 runtime/wechat/。WCDB.lib 只作为构建输入，不复制进 runtime。

    前置工具（不自动安装）：Git、CMake >= 3.20、Visual Studio 2022（含 C++ x64
    工具集 VC.Tools.x86.x64 与 Windows 10/11 SDK）。

.PARAMETER ProjectRootOverride
    项目根目录（默认取本脚本上一级）。用于测试。

.PARAMETER WcdbSourceDir
    复用已有的 WCDB v2.1.15 源码树（跳过 clone）。

.PARAMETER WcdbBuildDir
    WCDB CMake 构建目录（默认 build/cache/wcdb-build）。

.PARAMETER SkipWcdbBuild
    跳过 WCDB 的 CMake 配置/构建，直接复用 WcdbBuildDir\Release 下的
    WCDB.dll / WCDB.lib。

.PARAMETER SkipCliBuild
    跳过 wcdb_cli 构建，复用 build/cache/wcdb_cli-build\Release\wcdb_cli.exe。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\bootstrap_wechat_native.ps1
#>
[CmdletBinding()]
param(
    [string]$ProjectRootOverride = '',
    [string]$WcdbSourceDir = '',
    [string]$WcdbBuildDir = '',
    [switch]$SkipWcdbBuild,
    [switch]$SkipCliBuild
)

$ErrorActionPreference = 'Stop'

function Write-Step([string]$Message) { Write-Host "[bootstrap] $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host "[OK] $Message" -ForegroundColor Green }
function Fail([string]$Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
}

# project root
if ($ProjectRootOverride) {
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRootOverride -ErrorAction Stop).Path
}
else {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path
}

$RuntimeDir   = Join-Path $ProjectRoot 'runtime\wechat'
$CacheRoot    = Join-Path $ProjectRoot 'build\cache'
$CliSourceDir = Join-Path $ProjectRoot 'src\qq_chat_analyzer\native\wcdb_cli'

$WcdbRepoUrl = 'https://github.com/Tencent/wcdb.git'
$WcdbTag     = 'v2.1.15'
$PinnedSqlcipher = 'f049bed66ca26741f09a6e4f0603ed3af195ac96'
$PinnedZstd      = '69036dffe50f385bd3b7b187e3fd230f4b2ef97e'
# prerequisites
function Assert-CommandAvailable([string]$Name, [string]$Hint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Fail "缺少前置工具: $Name。$Hint"
    }
}

Assert-CommandAvailable 'git' '请安装 Git for Windows 并加入 PATH。'
Assert-CommandAvailable 'cmake' '请安装 CMake 3.20+ 并加入 PATH。'

$CmakeVersionLine = (cmake --version | Select-Object -First 1)
if ($CmakeVersionLine -notmatch '(\d+)\.(\d+)\.(\d+)') {
    Fail '无法解析 cmake 版本。'
}
$CmakeMajor = [int]$Matches[1]
$CmakeMinor = [int]$Matches[2]
if (($CmakeMajor -lt 3) -or ($CmakeMajor -eq 3 -and $CmakeMinor -lt 20)) {
    Fail "cmake 版本过低: $CmakeVersionLine，需要 3.20+。"
}

$Vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $Vswhere)) {
    Fail "缺少 Visual Studio Installer: $Vswhere"
}
$VsInstall = & $Vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $VsInstall) {
    Fail '缺少 VS2022 C++ x64 构建环境（VC.Tools.x86.x64）。请安装 Visual Studio 2022 的“使用 C++ 的桌面开发”工作负载。'
}
$VcToolsRoot = Join-Path $VsInstall 'VC\Tools\MSVC'
if (-not (Test-Path -LiteralPath $VcToolsRoot)) {
    Fail "缺少 MSVC 工具集: $VcToolsRoot"
}
$WindowsKitsLib = 'C:\Program Files (x86)\Windows Kits\10\Lib'
if (-not (Test-Path -LiteralPath $WindowsKitsLib)) {
    Fail "缺少 Windows SDK: $WindowsKitsLib"
}
Write-Ok "前置检查通过: git / cmake / VS2022 ($VsInstall)"

# source acquisition
if ($WcdbSourceDir) {
    $WcdbSrc = (Resolve-Path -LiteralPath $WcdbSourceDir -ErrorAction Stop).Path
    if (-not (Test-Path -LiteralPath (Join-Path $WcdbSrc 'src\CMakeLists.txt'))) {
        Fail "WcdbSourceDir 不是 WCDB 源码树（缺少 src\CMakeLists.txt）: $WcdbSrc"
    }
    Write-Step "复用已有 WCDB 源码: $WcdbSrc"
}
else {
    $WcdbSrc = Join-Path $CacheRoot 'wcdb-src'
    if (-not (Test-Path -LiteralPath (Join-Path $WcdbSrc 'src\CMakeLists.txt'))) {
        Write-Step "clone Tencent/wcdb tag $WcdbTag 到 $WcdbSrc"
        New-Item -ItemType Directory -Force -Path $CacheRoot | Out-Null
        git clone --recursive --branch $WcdbTag $WcdbRepoUrl $WcdbSrc
        if ($LASTEXITCODE -ne 0) {
            Fail "git clone 失败 (exit $LASTEXITCODE)。请检查网络与 GitHub 访问。"
        }
        Write-Ok 'WCDB 源码与子模块 clone 完成。'
    }
    else {
        Write-Step "复用已有 WCDB 源码: $WcdbSrc"
    }
}

# submodule pin verification
function Assert-PinnedHead([string]$RepoPath, [string]$Expected, [string]$Name) {
    if (-not (Test-Path -LiteralPath (Join-Path $RepoPath '.git'))) {
        Fail "子模块 '$Name' 缺失: $RepoPath（recursive clone 未完成？）"
    }
    $Head = (& git -c safe.directory='*' -C $RepoPath rev-parse HEAD 2>$null).Trim()
    if (-not $Head) {
        Fail "无法读取子模块 '$Name' 的 HEAD: $RepoPath"
    }
    if ($Head -ne $Expected) {
        Fail "子模块 '$Name' HEAD 与 pin 不一致: 期望 $Expected，实际 $Head。拒绝继续构建。"
    }
    Write-Ok "子模块 '$Name' 已固定: $Head"
}
Assert-PinnedHead (Join-Path $WcdbSrc 'sqlcipher') $PinnedSqlcipher 'sqlcipher'
Assert-PinnedHead (Join-Path $WcdbSrc 'zstd') $PinnedZstd 'zstd'
# WCDB build
if (-not $WcdbBuildDir) {
    $WcdbBuildDir = Join-Path $CacheRoot 'wcdb-build'
}
$WcdbBuild = (Resolve-Path -LiteralPath $WcdbBuildDir -ErrorAction SilentlyContinue).Path
if (-not $WcdbBuild) { $WcdbBuild = $WcdbBuildDir }
$WcdbDll = Join-Path $WcdbBuild 'Release\WCDB.dll'
$WcdbLib = Join-Path $WcdbBuild 'Release\WCDB.lib'

if (-not $SkipWcdbBuild) {
    Write-Step '配置 WCDB 构建 (VS2022 x64 Release, BUILD_SHARED_LIBS=ON, WCDB_ZSTD=ON)'
    if (-not (Test-Path -LiteralPath (Join-Path $WcdbBuild 'CMakeCache.txt'))) {
        cmake -S (Join-Path $WcdbSrc 'src') -B $WcdbBuild -G 'Visual Studio 17 2022' -A x64 `
            -DCMAKE_CONFIGURATION_TYPES=Release -DBUILD_SHARED_LIBS=ON -DWCDB_ZSTD=ON
        if ($LASTEXITCODE -ne 0) {
            Fail "WCDB CMake 配置失败 (exit $LASTEXITCODE)。"
        }
    }
    else {
        Write-Step "复用已有 WCDB 构建树: $WcdbBuild"
    }
    Write-Step '构建 WCDB (Release)'
    cmake --build $WcdbBuild --config Release --target WCDB
    if ($LASTEXITCODE -ne 0) {
        Fail "WCDB 构建失败 (exit $LASTEXITCODE)。"
    }
}
if (-not (Test-Path -LiteralPath $WcdbDll)) { Fail "未找到 WCDB.dll: $WcdbDll" }
if (-not (Test-Path -LiteralPath $WcdbLib)) { Fail "未找到 WCDB.lib: $WcdbLib" }
Write-Ok "WCDB 产物就绪: $WcdbDll / $WcdbLib"

# wcdb_cli build
$CliBuildDir = Join-Path $CacheRoot 'wcdb_cli-build'
$CliExe = Join-Path $CliBuildDir 'Release\wcdb_cli.exe'
if (-not $SkipCliBuild) {
    Write-Step '配置 wcdb_cli (参数化 WCDB_SOURCE_DIR / WCDB_LIBRARY)'
    if (-not (Test-Path -LiteralPath (Join-Path $CliBuildDir 'CMakeCache.txt'))) {
        cmake -S $CliSourceDir -B $CliBuildDir -G 'Visual Studio 17 2022' -A x64 `
            -DCMAKE_CONFIGURATION_TYPES=Release `
            "-DWCDB_SOURCE_DIR=$WcdbSrc" "-DWCDB_LIBRARY=$WcdbLib"
        if ($LASTEXITCODE -ne 0) {
            Fail "wcdb_cli CMake 配置失败 (exit $LASTEXITCODE)。"
        }
    }
    else {
        Write-Step "复用已有 wcdb_cli 构建树: $CliBuildDir"
    }
    Write-Step '构建 wcdb_cli (Release)'
    cmake --build $CliBuildDir --config Release
    if ($LASTEXITCODE -ne 0) {
        Fail "wcdb_cli 构建失败 (exit $LASTEXITCODE)。"
    }
}
if (-not (Test-Path -LiteralPath $CliExe)) { Fail "未找到 wcdb_cli.exe: $CliExe" }

# artifact checks
function Assert-NonEmpty([string]$Path, [string]$Label) {
    $Item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($Item.Length -eq 0) { Fail "产物 '$Label' 为空: $Path" }
    Write-Ok "$Label ($($Item.Length) bytes): $Path"
}
Assert-NonEmpty $WcdbDll 'WCDB.dll'
Assert-NonEmpty $WcdbLib 'WCDB.lib'
Assert-NonEmpty $CliExe 'wcdb_cli.exe'

# sync to runtime/wechat
Write-Step "同步运行产物到 $RuntimeDir"
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
Copy-Item -LiteralPath $WcdbDll -Destination (Join-Path $RuntimeDir 'WCDB.dll') -Force
Copy-Item -LiteralPath $CliExe -Destination (Join-Path $RuntimeDir 'wcdb_cli.exe') -Force

$RtDll = Get-Item -LiteralPath (Join-Path $RuntimeDir 'WCDB.dll')
$RtExe = Get-Item -LiteralPath (Join-Path $RuntimeDir 'wcdb_cli.exe')
if ($RtDll.Length -eq 0 -or $RtExe.Length -eq 0) {
    Fail 'runtime/wechat 同步后产物为空。'
}
$RtDllHash = (Get-FileHash -LiteralPath $RtDll.FullName -Algorithm SHA256).Hash
$SrcDllHash = (Get-FileHash -LiteralPath $WcdbDll -Algorithm SHA256).Hash
$RtExeHash = (Get-FileHash -LiteralPath $RtExe.FullName -Algorithm SHA256).Hash
$SrcExeHash = (Get-FileHash -LiteralPath $CliExe -Algorithm SHA256).Hash
if ($RtDllHash -ne $SrcDllHash -or $RtExeHash -ne $SrcExeHash) {
    Fail 'runtime 同步校验失败：哈希不一致。'
}

Write-Ok "runtime/wechat/WCDB.dll 已同步 (SHA256=$RtDllHash)"
Write-Ok "runtime/wechat/wcdb_cli.exe 已同步 (SHA256=$RtExeHash)"
Write-Host ''
Write-Host 'bootstrap_wechat_native.ps1 完成。' -ForegroundColor Green
