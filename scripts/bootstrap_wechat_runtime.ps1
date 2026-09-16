<#
.SYNOPSIS
    从官方来源恢复微信运行时所需的 Node.js 与 Koffi 依赖。

.DESCRIPTION
    clean clone 只恢复 runtime\wechat 下的两项依赖：

      * node.exe —— Node.js 官方 win-x64 zip，只取其中的 node.exe；
      * node_modules\koffi\ —— npm 官方 registry tarball，只取 index.js、
        build\koffi\win32_x64\koffi.node 与 LICENSE.txt。

    流程固定为"先全部校验、再一次性安装"，任何校验失败都整体失败并保持
    runtime\wechat 原样不变：

      1. 读取来源 pin 文件 scripts\wechat_runtime_pins.json；
      2. 校验来源 URL 必须是官方主机（nodejs.org / registry.npmjs.org）；
      3. 下载（或复用本地归档）到临时目录；
      4. 校验归档 SHA256、npm dist.integrity(SHA-512)、dist.shasum(SHA-1)；
      5. 解包到临时目录，校验 node.exe 的 SHA256、以及 Koffi 白名单成员存在；
      6. 只有以上全部通过，才写入 runtime\wechat；
      7. 无论成功还是失败，都清理临时目录。

    不执行 npm 安装，不运行任何第三方 install script，不复制其它平台的
    native addon，也不使用第三方镜像。其它原生引导产物不属于本脚本范围。

.PARAMETER ProjectRootOverride
    产品根目录（默认取本脚本上一级）。用于隔离测试或指定目标位置。

.PARAMETER NodeArchivePath
    复用已经下载好的官方 Node.js zip，跳过下载（仍按 pin 校验）。

.PARAMETER KoffiTarballPath
    复用已经下载好的官方 Koffi tarball，跳过下载（仍按 pin 校验）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\bootstrap_wechat_runtime.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\bootstrap_wechat_runtime.ps1 `
        -ProjectRootOverride D:\scratch\portable-root
#>
[CmdletBinding()]
param(
    [string]$ProjectRootOverride = '',
    [string]$NodeArchivePath = '',
    [string]$KoffiTarballPath = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# 本阶段只允许这两个目标，且都固定在 runtime\wechat 之下。
$NodeTargetRelativePath = 'runtime\wechat\node.exe'
$KoffiTargetRelativePath = 'runtime\wechat\node_modules\koffi'

# 结构性白名单：koffi tarball 里只有这三个成员会进入 runtime，其余内容
# （其它平台 addon、C++ 源码、README 等）一律丢弃。
$KoffiMembers = @(
    @{
        Source = 'package/index.js'
        Target = 'index.js'
    }
    @{
        Source = 'package/build/koffi/win32_x64/koffi.node'
        Target = 'build/koffi/win32_x64/koffi.node'
    }
    @{
        Source = 'package/LICENSE.txt'
        Target = 'LICENSE.txt'
    }
)

$OfficialNodeHosts = @('nodejs.org')
$OfficialKoffiHosts = @('registry.npmjs.org')

function Write-Step([string]$Message) {
    Write-Host "[bootstrap] $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Fail([string]$Message) {
    throw [System.InvalidOperationException]::new($Message)
}

function Get-RuntimePins {
    if (-not (Test-Path -LiteralPath $PinsPath -PathType Leaf)) {
        Fail "缺少来源 pin 文件: $PinsPath"
    }
    $Pins = (Get-Content -LiteralPath $PinsPath -Raw -Encoding UTF8) | ConvertFrom-Json
    if (-not $Pins.node) { Fail "pin 文件缺少 'node' 段: $PinsPath" }
    if (-not $Pins.koffi) { Fail "pin 文件缺少 'koffi' 段: $PinsPath" }
    foreach ($Field in @('version', 'archiveUrl', 'archiveSha256', 'archiveRoot', 'executableSha256')) {
        if (-not $Pins.node.$Field) { Fail "pin 文件缺少 'node.$Field': $PinsPath" }
    }
    foreach ($Field in @('version', 'tarballUrl', 'tarballIntegrity', 'tarballSha1')) {
        if (-not $Pins.koffi.$Field) { Fail "pin 文件缺少 'koffi.$Field': $PinsPath" }
    }
    $ArchiveRoot = [string]$Pins.node.archiveRoot
    if ($ArchiveRoot -match '[\\/]' -or $ArchiveRoot -eq '.') {
        Fail "pin 的 node.archiveRoot 必须是归档内的单层目录名: $ArchiveRoot"
    }
    return $Pins
}

function Assert-OfficialUrl([string]$Url, [string[]]$AllowedHosts, [string]$Label) {
    $Uri = $null
    if (-not [System.Uri]::TryCreate($Url, [System.UriKind]::Absolute, [ref]$Uri)) {
        Fail "$Label 不是绝对 URL: $Url"
    }
    if ($Uri.Scheme -cne 'https') {
        Fail "$Label 必须使用 https: $Url"
    }
    if ($AllowedHosts -notcontains $Uri.Host) {
        Fail "$Label 主机不在允许清单内: $($Uri.Host)"
    }
    Write-Ok "$Label 来源主机已确认: $($Uri.Host)"
}

function Get-FileSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-FileSha256([string]$Path, [string]$Expected, [string]$Label) {
    $Actual = Get-FileSha256 -Path $Path
    if ($Actual -ne $Expected.ToLowerInvariant()) {
        Fail "$Label SHA256 不匹配: 期望 $Expected，实际 $Actual"
    }
    Write-Ok "$Label SHA256 校验通过"
}

function Get-FileSha512Base64([string]$Path) {
    $Hasher = [System.Security.Cryptography.SHA512]::Create()
    $Stream = [System.IO.File]::OpenRead($Path)
    try {
        return [Convert]::ToBase64String($Hasher.ComputeHash($Stream))
    }
    finally {
        $Stream.Dispose()
        $Hasher.Dispose()
    }
}

function Save-OfficialArchive([string]$Url, [string]$Destination, [string]$Label) {
    Write-Step "下载 $Label"
    if ($PSVersionTable.PSVersion.Major -lt 6) {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
    }
    else {
        Invoke-WebRequest -Uri $Url -OutFile $Destination
    }
    if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
        Fail "下载失败: $Url"
    }
    Write-Ok "已下载 $Label"
}

function Get-NodeArchive([string]$Url) {
    if ($NodeArchivePath) {
        $Local = (Resolve-Path -LiteralPath $NodeArchivePath -ErrorAction Stop).Path
        Write-Step "复用本地 Node.js zip（仍按 pin 校验）: $Local"
        return $Local
    }
    $Downloaded = Join-Path $TempRoot 'node-win-x64.zip'
    Save-OfficialArchive -Url $Url -Destination $Downloaded -Label 'Node.js zip'
    return $Downloaded
}

function Get-KoffiTarball([string]$Url) {
    if ($KoffiTarballPath) {
        $Local = (Resolve-Path -LiteralPath $KoffiTarballPath -ErrorAction Stop).Path
        Write-Step "复用本地 Koffi tarball（仍按 pin 校验）: $Local"
        return $Local
    }
    $Downloaded = Join-Path $TempRoot 'koffi.tgz'
    Save-OfficialArchive -Url $Url -Destination $Downloaded -Label 'koffi tarball'
    return $Downloaded
}

function Assert-NodeArchive {
    param(
        [Parameter(Mandatory = $true)][string]$ArchivePath,
        [Parameter(Mandatory = $true)]$NodePin
    )

    Assert-FileSha256 -Path $ArchivePath -Expected ([string]$NodePin.archiveSha256) -Label 'Node.js zip'

    $Expanded = Join-Path $TempRoot 'node-expanded'
    New-Item -ItemType Directory -Force -Path $Expanded | Out-Null
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $Expanded -Force

    $Executable = Join-Path (Join-Path $Expanded ([string]$NodePin.archiveRoot)) 'node.exe'
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        Fail "Node.js zip 内缺少 node.exe: $($NodePin.archiveRoot) 目录下未找到"
    }
    Assert-FileSha256 -Path $Executable -Expected ([string]$NodePin.executableSha256) -Label 'node.exe'
    return $Executable
}

function Assert-KoffiTarball {
    param(
        [Parameter(Mandatory = $true)][string]$TarballPath,
        [Parameter(Mandatory = $true)]$KoffiPin
    )

    $Integrity = [string]$KoffiPin.tarballIntegrity
    if (-not $Integrity.StartsWith('sha512-')) {
        Fail "pin 的 koffi.tarballIntegrity 必须是 sha512- 形式: $Integrity"
    }
    $ActualIntegrity = 'sha512-' + (Get-FileSha512Base64 -Path $TarballPath)
    if ($ActualIntegrity -cne $Integrity) {
        Fail "koffi tarball SHA-512 (dist.integrity) 不匹配: 期望 $Integrity，实际 $ActualIntegrity"
    }
    Write-Ok 'koffi tarball SHA-512 (dist.integrity) 校验通过'

    $ExpectedSha1 = ([string]$KoffiPin.tarballSha1).ToLowerInvariant()
    $ActualSha1 = (Get-FileHash -LiteralPath $TarballPath -Algorithm SHA1).Hash.ToLowerInvariant()
    if ($ActualSha1 -ne $ExpectedSha1) {
        Fail "koffi tarball SHA-1 (dist.shasum) 不匹配: 期望 $ExpectedSha1，实际 $ActualSha1"
    }
    Write-Ok 'koffi tarball SHA-1 (dist.shasum) 校验通过'

    $Expanded = Join-Path $TempRoot 'koffi-expanded'
    New-Item -ItemType Directory -Force -Path $Expanded | Out-Null
    & tar -xzf $TarballPath -C $Expanded
    if ($LASTEXITCODE -ne 0) {
        Fail "解包 koffi tarball 失败 (tar exit $LASTEXITCODE)"
    }

    $Verified = @()
    foreach ($Member in $KoffiMembers) {
        $Candidate = Join-Path $Expanded (([string]$Member.Source) -replace '/', '\')
        if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
            Fail "koffi 包内缺少白名单成员: $($Member.Source)"
        }
        $Verified += $Candidate
    }
    Write-Ok "koffi 白名单成员齐全 ($($KoffiMembers.Count) 项)"
    return , $Verified
}

function Install-NodeRuntime {
    param(
        [Parameter(Mandatory = $true)][string]$VerifiedExecutable,
        [Parameter(Mandatory = $true)]$NodePin
    )

    $Destination = Join-Path $ProjectRoot $NodeTargetRelativePath
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Copy-Item -LiteralPath $VerifiedExecutable -Destination $Destination -Force
    Assert-FileSha256 -Path $Destination -Expected ([string]$NodePin.executableSha256) -Label 'runtime\wechat\node.exe'
    Write-Ok 'runtime\wechat\node.exe 已恢复'
}

function Install-KoffiRuntime {
    param(
        [Parameter(Mandatory = $true)][string[]]$VerifiedSources
    )

    $TargetRoot = Join-Path $ProjectRoot $KoffiTargetRelativePath
    # 先整体删除旧目录、再按白名单回填：上游包里的其它平台 addon 与历史残留
    # 因此永远不会留在 runtime 里。
    if (Test-Path -LiteralPath $TargetRoot) {
        Remove-Item -LiteralPath $TargetRoot -Recurse -Force
    }

    for ($Index = 0; $Index -lt $KoffiMembers.Count; $Index++) {
        $Member = $KoffiMembers[$Index]
        $Target = Join-Path $TargetRoot (([string]$Member.Target) -replace '/', '\')
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
        Copy-Item -LiteralPath $VerifiedSources[$Index] -Destination $Target -Force
    }

    $Expected = @($KoffiMembers | ForEach-Object { [string]$_.Target })
    $Installed = @(
        Get-ChildItem -LiteralPath $TargetRoot -Recurse -File -Force |
            ForEach-Object { $_.FullName.Substring($TargetRoot.Length + 1) -replace '\\', '/' }
    )
    $Unexpected = @($Installed | Where-Object { $Expected -notcontains $_ })
    if ($Unexpected.Count -gt 0) {
        Fail ('koffi 目录出现白名单以外的成员: ' + ($Unexpected -join ', '))
    }
    foreach ($ExpectedTarget in $Expected) {
        if ($Installed -notcontains $ExpectedTarget) {
            Fail "koffi 安装不完整: $ExpectedTarget"
        }
    }
    Write-Ok "runtime\wechat\node_modules\koffi 已恢复 ($($Expected.Count) 项)"
}

$PinsPath = Join-Path $PSScriptRoot 'wechat_runtime_pins.json'
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('echo-wechat-runtime-' + [guid]::NewGuid().ToString('N'))

# 失败状态用显式布尔量：任何异常都必然导致非 0 退出，不依赖消息是否非空。
$Failed = $false
$FailureMessage = ''
try {
    if (-not (Get-Command tar -ErrorAction SilentlyContinue)) {
        Fail '缺少前置工具: tar（Windows 10 1803+ 自带）。'
    }

    if ($ProjectRootOverride) {
        $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRootOverride -ErrorAction Stop).Path
    }
    else {
        $ProjectRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot) -ErrorAction Stop).Path
    }

    $Pins = Get-RuntimePins
    Assert-OfficialUrl -Url ([string]$Pins.node.archiveUrl) -AllowedHosts $OfficialNodeHosts -Label 'node.archiveUrl'
    Assert-OfficialUrl -Url ([string]$Pins.koffi.tarballUrl) -AllowedHosts $OfficialKoffiHosts -Label 'koffi.tarballUrl'

    New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null
    Write-Step "临时工作目录: $TempRoot"

    # 先完成全部来源校验，再开始安装：任何校验失败都不会改动 runtime。
    $NodeArchive = Get-NodeArchive -Url ([string]$Pins.node.archiveUrl)
    $NodeExecutable = Assert-NodeArchive -ArchivePath $NodeArchive -NodePin $Pins.node
    $KoffiTarball = Get-KoffiTarball -Url ([string]$Pins.koffi.tarballUrl)
    $KoffiSources = Assert-KoffiTarball -TarballPath $KoffiTarball -KoffiPin $Pins.koffi

    Install-NodeRuntime -VerifiedExecutable $NodeExecutable -NodePin $Pins.node
    Install-KoffiRuntime -VerifiedSources $KoffiSources
}
catch {
    $Failed = $true
    $FailureMessage = $_.Exception.Message
    if (-not $FailureMessage) {
        $FailureMessage = $_.Exception.GetType().FullName
    }
}
finally {
    if ($TempRoot -and (Test-Path -LiteralPath $TempRoot)) {
        Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if ($Failed) {
    if (-not $FailureMessage) {
        $FailureMessage = 'bootstrap 失败：异常未提供消息。'
    }
    Write-Host "[ERROR] $FailureMessage" -ForegroundColor Red
    exit 1
}

Write-Host ''
Write-Host 'bootstrap_wechat_runtime.ps1 完成。' -ForegroundColor Green
