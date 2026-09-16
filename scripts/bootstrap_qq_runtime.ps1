<#
.SYNOPSIS
    从官方 QCE 发布资产恢复完整的 QQ 运行时（runtime\qq）。

.DESCRIPTION
    clean clone 只恢复 runtime\qq 下的完整上游运行时：QCE 官方 Windows x64
    Shell 发布资产（内含 NapCat Shell、QCE 插件、qce-server.exe、node_modules、
    native addons、static/qce 前端与 QCE 启动脚本）。

    来源、版本与全部校验值只来自 scripts\qq_runtime_pins.json；本脚本不维护
    第二套版本或哈希。

    流程固定为"先全部校验、再一次性替换"：

      1. 读取来源 pin 文件 scripts\qq_runtime_pins.json；
      2. 校验来源 URL 必须是官方发布主机；
      3. 下载（或复用本地归档）到临时目录；
      4. 校验归档大小与 SHA256；
      5. 只读扫描归档条目：拒绝绝对路径、穿越路径段与重复成员，
         并逐项校验被 pin 的上游成员 SHA256；
      6. 解包到临时目录；
      7. 删除机器状态与上游逐机配置（runtime contract 的 privatePaths +
         pin 的 excludedPaths）；
      8. 校验上游 launcher-user.bat 的 SHA256，确定性施加 Echo 补丁，
         再校验最终 SHA256；
      9. 校验 runtime contract、被 pin 成员与私有状态；
     10. 只有以上全部通过，才在 runtime\ 下用 staging + 交换 + 回滚备份的方式
         原子式替换 qq 目录；
     11. finally 清理临时目录、staging 与备份；
     12. 任一异常 exit 1。

    不执行任何包管理器安装，不复制本地旧 runtime，不使用第三方镜像。其它原生
    引导产物（微信）不属于本脚本范围。

.PARAMETER ProjectRootOverride
    产品根目录（默认取本脚本上一级）。用于隔离测试或指定目标位置。

.PARAMETER QceArchivePath
    复用已下载好的官方 QCE 发布资产，跳过下载（仍按 pin 完整校验）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\bootstrap_qq_runtime.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\bootstrap_qq_runtime.ps1 `
        -ProjectRootOverride D:\scratch\portable-root
#>
[CmdletBinding()]
param(
    [string]$ProjectRootOverride = '',
    [string]$QceArchivePath = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# 本阶段只允许这一个目标，且固定在 runtime\qq 之下。
$QqTargetRelativePath = 'runtime\qq'

# 归档下载只允许官方发布主机及其重定向落点。
$OfficialArchiveHosts = @('github.com', 'objects.githubusercontent.com')

$RuntimeContract = $null

function Write-Step([string]$Message) {
    Write-Host "[bootstrap] $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Fail([string]$Message) {
    throw [System.InvalidOperationException]::new($Message)
}

function Get-RuntimeContract {
    if ($null -ne $RuntimeContract) {
        return $RuntimeContract
    }
    if (-not (Test-Path -LiteralPath $RuntimeContractPath -PathType Leaf)) {
        Fail 'Runtime contract manifest is missing: scripts\windows_runtime_manifest.json'
    }
    $Contract = (
        Get-Content -LiteralPath $RuntimeContractPath -Raw -Encoding UTF8
    ) | ConvertFrom-Json
    if (-not $Contract.requirements -or -not $Contract.privatePaths) {
        Fail 'Runtime contract manifest is incomplete: scripts\windows_runtime_manifest.json'
    }
    $script:RuntimeContract = $Contract
    return $script:RuntimeContract
}

function Assert-Sha256Text([string]$Value, [string]$Label) {
    if ($Value -notmatch '^[0-9a-f]{64}$') {
        Fail "$Label 必须是 64 位小写十六进制 SHA256: $Value"
    }
}

function Get-QqRuntimePins {
    if (-not (Test-Path -LiteralPath $PinsPath -PathType Leaf)) {
        Fail "缺少来源 pin 文件: $PinsPath"
    }
    $Pins = (Get-Content -LiteralPath $PinsPath -Raw -Encoding UTF8) | ConvertFrom-Json
    if (-not $Pins.qce) { Fail "pin 文件缺少 'qce' 段: $PinsPath" }
    if (-not $Pins.launcherPatch) { Fail "pin 文件缺少 'launcherPatch' 段: $PinsPath" }
    if (-not $Pins.requiredFiles) { Fail "pin 文件缺少 'requiredFiles' 段: $PinsPath" }
    if (-not $Pins.excludedPaths) { Fail "pin 文件缺少 'excludedPaths' 段: $PinsPath" }

    foreach ($Field in @(
            'version', 'project', 'license', 'releaseUrl', 'archiveUrl',
            'archiveSha256', 'archiveSizeBytes', 'archiveRoot',
            'bundledNapCatVersion', 'bundledNapCatProject', 'bundledNapCatLicense'
        )) {
        if (-not $Pins.qce.$Field) { Fail "pin 文件缺少 'qce.$Field': $PinsPath" }
    }
    foreach ($Field in @(
            'path', 'upstreamSha256', 'patchedSha256', 'anchor', 'replacement', 'addedLine'
        )) {
        if (-not $Pins.launcherPatch.$Field) {
            Fail "pin 文件缺少 'launcherPatch.$Field': $PinsPath"
        }
    }

    $ArchiveSha256 = ([string]$Pins.qce.archiveSha256).ToLowerInvariant()
    Assert-Sha256Text -Value $ArchiveSha256 -Label 'qce.archiveSha256'
    $Pins.qce.archiveSha256 = $ArchiveSha256
    $UpstreamLauncher = ([string]$Pins.launcherPatch.upstreamSha256).ToLowerInvariant()
    $PatchedLauncher = ([string]$Pins.launcherPatch.patchedSha256).ToLowerInvariant()
    Assert-Sha256Text -Value $UpstreamLauncher -Label 'launcherPatch.upstreamSha256'
    Assert-Sha256Text -Value $PatchedLauncher -Label 'launcherPatch.patchedSha256'
    $Pins.launcherPatch.upstreamSha256 = $UpstreamLauncher
    $Pins.launcherPatch.patchedSha256 = $PatchedLauncher

    foreach ($Property in $Pins.requiredFiles.PSObject.Properties) {
        $Value = ([string]$Property.Value).ToLowerInvariant()
        Assert-Sha256Text -Value $Value -Label "requiredFiles.$($Property.Name)"
        $Property.Value = $Value
    }

    $ArchiveRoot = [string]$Pins.qce.archiveRoot
    if (-not $ArchiveRoot -or $ArchiveRoot -match '[\\/]' -or $ArchiveRoot -match '^\.{1,2}$') {
        Fail "pin 的 qce.archiveRoot 必须是归档内的单层目录名: $ArchiveRoot"
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

function Get-ZipEntrySha256([System.IO.Compression.ZipArchiveEntry]$Entry) {
    $Hasher = [System.Security.Cryptography.SHA256]::Create()
    $Stream = $Entry.Open()
    try {
        $Digest = $Hasher.ComputeHash($Stream)
        return (($Digest | ForEach-Object { $_.ToString('x2') }) -join '')
    }
    finally {
        $Stream.Dispose()
        $Hasher.Dispose()
    }
}

function Get-QceArchive([string]$Url) {
    if ($QceArchivePath) {
        $Local = (Resolve-Path -LiteralPath $QceArchivePath -ErrorAction Stop).Path
        Write-Step "复用本地 QCE 发布资产（仍按 pin 完整校验）: $Local"
        return $Local
    }

    $Downloaded = Join-Path $TempRoot 'qce-asset.zip'
    Write-Step '下载官方 QCE Windows x64 发布资产'
    $Attempts = 3
    for ($Attempt = 1; $Attempt -le $Attempts; $Attempt++) {
        try {
            if ($PSVersionTable.PSVersion.Major -lt 6) {
                [System.Net.ServicePointManager]::SecurityProtocol = (
                    [System.Net.SecurityProtocolType]::Tls12
                )
                Invoke-WebRequest -Uri $Url -OutFile $Downloaded -UseBasicParsing
            }
            else {
                Invoke-WebRequest -Uri $Url -OutFile $Downloaded
            }
            if (Test-Path -LiteralPath $Downloaded -PathType Leaf) {
                Write-Ok '已下载 QCE 发布资产'
                return $Downloaded
            }
        }
        catch {
            if ($Attempt -ge $Attempts) {
                throw
            }
            Write-Step "下载失败（第 $Attempt 次），重试: $($_.Exception.Message)"
            Remove-Item -LiteralPath $Downloaded -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
    }
    Fail "下载失败: $Url"
}

function Assert-QceArchiveFile {
    param(
        [Parameter(Mandatory = $true)][string]$ArchivePath,
        [Parameter(Mandatory = $true)]$Pins
    )

    if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) {
        Fail "QCE 发布资产不存在: $ArchivePath"
    }
    $ActualSize = (Get-Item -LiteralPath $ArchivePath).Length
    $ExpectedSize = [long]$Pins.qce.archiveSizeBytes
    if ($ActualSize -ne $ExpectedSize) {
        Fail "QCE 发布资产 size 不匹配: 期望 $ExpectedSize 字节，实际 $ActualSize 字节"
    }
    Write-Ok 'QCE 发布资产大小校验通过'
    Assert-FileSha256 -Path $ArchivePath -Expected ([string]$Pins.qce.archiveSha256) -Label 'QCE 发布资产'
}

function Assert-QceArchiveEntries {
    param(
        [Parameter(Mandatory = $true)][string]$ArchivePath,
        [Parameter(Mandatory = $true)]$Pins
    )

    $RootPrefix = ([string]$Pins.qce.archiveRoot) + '/'
    $Expected = @{}
    foreach ($Property in $Pins.requiredFiles.PSObject.Properties) {
        $Expected[[string]$Property.Name] = ([string]$Property.Value).ToLowerInvariant()
    }
    $LauncherRelative = ([string]$Pins.launcherPatch.path) -replace '\\', '/'
    $Expected[$LauncherRelative] = ([string]$Pins.launcherPatch.upstreamSha256).ToLowerInvariant()

    $Archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
    try {
        $Members = @{}
        foreach ($Entry in $Archive.Entries) {
            $Name = ([string]$Entry.FullName) -replace '\\', '/'
            if ($Name.StartsWith('/') -or $Name.StartsWith('\') -or $Name -match '^[A-Za-z]:') {
                Fail "归档成员必须是相对路径: $Name"
            }
            $Segments = @($Name -split '/')
            # 拒绝点路径段与空路径段（父目录穿越防护）。
            $Invalid = @($Segments | Where-Object { $_ -match '^\.{0,2}$' })
            if ($Invalid.Count -gt 0) {
                Fail "归档成员路径非法（穿越或空路径段）: $Name"
            }
            if (-not $Name.StartsWith($RootPrefix)) {
                Fail (
                    "归档成员不在 pin 的顶层目录内: $Name" +
                    " (期望顶层目录 '$(($Pins.qce.archiveRoot))')"
                )
            }
            $Relative = $Name.Substring($RootPrefix.Length)
            if ($Members.ContainsKey($Relative)) {
                Fail "归档成员重复: $Name"
            }
            $Members[$Relative] = $Entry
        }

        foreach ($Relative in @($Expected.Keys)) {
            if (-not $Members.ContainsKey($Relative)) {
                Fail "归档缺少被 pin 的上游成员: $Relative"
            }
            $Actual = Get-ZipEntrySha256 -Entry $Members[$Relative]
            if ($Actual -ne $Expected[$Relative]) {
                Fail "归档成员 SHA256 不匹配: $Relative 期望 $($Expected[$Relative])，实际 $Actual"
            }
        }
        Write-Ok "归档条目与 $($Expected.Count) 项被 pin 上游成员校验通过"
    }
    finally {
        $Archive.Dispose()
    }
}

function Expand-QceArchive {
    param(
        [Parameter(Mandatory = $true)][string]$ArchivePath,
        [Parameter(Mandatory = $true)]$Pins
    )

    $ExpandedRoot = Join-Path $TempRoot 'expanded'
    New-Item -ItemType Directory -Force -Path $ExpandedRoot | Out-Null
    [System.IO.Compression.ZipFile]::ExtractToDirectory($ArchivePath, $ExpandedRoot)

    $RuntimeRoot = Join-Path $ExpandedRoot ([string]$Pins.qce.archiveRoot)
    if (-not (Test-Path -LiteralPath $RuntimeRoot -PathType Container)) {
        Fail "解包后缺少 pin 的顶层目录: $($Pins.qce.archiveRoot)"
    }
    Write-Ok 'QCE 发布资产已解包到临时目录'
    return $RuntimeRoot
}

function Get-ExcludedRelativePaths($Pins) {
    $Paths = New-Object System.Collections.Generic.List[string]
    foreach ($Entry in $Pins.excludedPaths) {
        $Relative = ([string]$Entry) -replace '\\', '/'
        if ($Relative -and -not $Paths.Contains($Relative)) {
            $Paths.Add($Relative)
        }
    }
    foreach ($Private in (Get-RuntimeContract).privatePaths) {
        if ([string]$Private.source -ne 'qq') { continue }
        $Relative = ([string]$Private.path) -replace '\\', '/'
        if ($Relative.StartsWith('qq/')) { $Relative = $Relative.Substring(3) }
        if ($Relative -and -not $Paths.Contains($Relative)) {
            $Paths.Add($Relative)
        }
    }
    return , $Paths.ToArray()
}

function Assert-ExcludedRuntimeStateAbsent {
    param(
        [Parameter(Mandatory = $true)][string]$RuntimeRoot,
        [Parameter(Mandatory = $true)]$Pins,
        [Parameter(Mandatory = $true)][string]$Label
    )

    foreach ($Relative in (Get-ExcludedRelativePaths -Pins $Pins)) {
        $Target = Join-Path $RuntimeRoot ($Relative -replace '/', '\')
        if (Test-Path -LiteralPath $Target) {
            Fail "$Label 仍包含被排除的运行时状态: $Relative"
        }
    }
    Write-Ok "$Label 不含任何被排除的运行时状态"
}

function Remove-ExcludedRuntimeState {
    param(
        [Parameter(Mandatory = $true)][string]$RuntimeRoot,
        [Parameter(Mandatory = $true)]$Pins
    )

    foreach ($Relative in (Get-ExcludedRelativePaths -Pins $Pins)) {
        $Target = Join-Path $RuntimeRoot ($Relative -replace '/', '\')
        if (Test-Path -LiteralPath $Target) {
            Remove-Item -LiteralPath $Target -Recurse -Force
        }
    }
    Write-Ok '已清除机器状态与上游逐机配置'
}

function Update-LauncherUserBatch {
    param(
        [Parameter(Mandatory = $true)][string]$RuntimeRoot,
        [Parameter(Mandatory = $true)]$Pins
    )

    $Relative = ([string]$Pins.launcherPatch.path) -replace '\\', '/'
    $Target = Join-Path $RuntimeRoot ($Relative -replace '/', '\')
    if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
        Fail "上游 launcher 缺失: $Relative"
    }
    Assert-FileSha256 -Path $Target -Expected ([string]$Pins.launcherPatch.upstreamSha256) -Label "上游 $Relative"

    # Latin1 逐字节往返：补丁只替换锚点，不改动其它字节、编码或换行。
    $Encoding = [System.Text.Encoding]::GetEncoding(28591)
    $Text = $Encoding.GetString([System.IO.File]::ReadAllBytes($Target))
    $Anchor = [string]$Pins.launcherPatch.anchor
    $Replacement = [string]$Pins.launcherPatch.replacement
    $Occurrences = ([regex]::Matches($Text, [regex]::Escape($Anchor))).Count
    if ($Occurrences -ne 1) {
        Fail "上游 launcher 的补丁锚点必须恰好出现一次，实际 $Occurrences 次: $Relative"
    }
    if (-not $Text.EndsWith($Anchor)) {
        Fail "上游 launcher 的补丁锚点必须位于文件末尾: $Relative"
    }

    $Patched = $Text.Substring(0, $Text.Length - $Anchor.Length) + $Replacement
    $AddedLine = [string]$Pins.launcherPatch.addedLine
    if (([regex]::Matches($Patched, [regex]::Escape($AddedLine))).Count -ne 1) {
        Fail "Echo 补丁必须恰好插入一次: $Relative"
    }
    [System.IO.File]::WriteAllBytes($Target, $Encoding.GetBytes($Patched))
    Assert-FileSha256 -Path $Target -Expected ([string]$Pins.launcherPatch.patchedSha256) -Label "Echo 补丁后的 $Relative"
}

function Assert-PinnedRuntimeFiles {
    param(
        [Parameter(Mandatory = $true)][string]$RuntimeRoot,
        [Parameter(Mandatory = $true)]$Pins
    )

    foreach ($Property in $Pins.requiredFiles.PSObject.Properties) {
        $Relative = [string]$Property.Name
        $Target = Join-Path $RuntimeRoot ($Relative -replace '/', '\')
        if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
            Fail "runtime 缺少被 pin 的上游成员: $Relative"
        }
        $Actual = Get-FileSha256 -Path $Target
        $Expected = ([string]$Property.Value).ToLowerInvariant()
        if ($Actual -ne $Expected) {
            Fail "runtime\$($Relative -replace '/', '\') SHA256 不匹配: 期望 $Expected，实际 $Actual"
        }
    }
    $PinnedCount = @($Pins.requiredFiles.PSObject.Properties).Count
    Write-Ok "runtime 内 $PinnedCount 项被 pin 上游成员校验通过"
}

function Assert-QqRuntimeContract {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Phase
    )

    foreach ($Requirement in (Get-RuntimeContract).requirements) {
        if ([string]$Requirement.source -ne 'qq') { continue }
        $Relative = ([string]$Requirement.path) -replace '\\', '/'
        if ($Relative.StartsWith('qq/')) { $Relative = $Relative.Substring(3) }
        $Display = 'runtime\qq\' + ($Relative -replace '/', '\')
        $Target = Join-Path $Root ($Relative -replace '/', '\')
        $Type = [string]$Requirement.type
        if ($Type -eq 'file') {
            if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
                Fail "Runtime contract is not satisfied ($Phase): missing $Display"
            }
        }
        elseif ($Type -eq 'non-empty-directory') {
            if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
                Fail "Runtime contract is not satisfied ($Phase): missing $Display"
            }
            if (@(Get-ChildItem -LiteralPath $Target -Force).Count -eq 0) {
                Fail "Runtime contract is not satisfied ($Phase): empty $Display"
            }
        }
        else {
            Fail "未知的 runtime contract 类型 '$Type': $Display"
        }
    }
    Write-Ok "runtime contract 校验通过 ($Phase)"
}

function Install-QqRuntime {
    param(
        [Parameter(Mandatory = $true)][string]$PreparedRoot,
        [Parameter(Mandatory = $true)][string]$RuntimeParent,
        [Parameter(Mandatory = $true)][string]$TargetRoot,
        [Parameter(Mandatory = $true)][string]$StagingRoot,
        [Parameter(Mandatory = $true)][string]$BackupRoot
    )

    # 目标 runtime 只被整体替换：先在同卷 staging 里落盘，再改名交换，
    # 旧目录短暂保留为回滚备份。
    New-Item -ItemType Directory -Force -Path $RuntimeParent | Out-Null
    if (Test-Path -LiteralPath $StagingRoot) {
        Remove-Item -LiteralPath $StagingRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $StagingRoot | Out-Null
    Get-ChildItem -LiteralPath $PreparedRoot -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $StagingRoot -Recurse -Force
    }

    if (Test-Path -LiteralPath $TargetRoot) {
        Move-Item -LiteralPath $TargetRoot -Destination $BackupRoot
    }
    Move-Item -LiteralPath $StagingRoot -Destination $TargetRoot
    Write-Ok 'runtime\qq 已整体替换'
}

$PinsPath = Join-Path $PSScriptRoot 'qq_runtime_pins.json'
$RuntimeContractPath = Join-Path $PSScriptRoot 'windows_runtime_manifest.json'
$RunId = [guid]::NewGuid().ToString('N')
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('echo-qq-runtime-' + $RunId)
$StagingRoot = ''
$BackupRoot = ''
$TargetRoot = ''

# 失败状态用显式布尔量：任何异常都必然导致非 0 退出，不依赖消息是否非空。
$Failed = $false
$FailureMessage = ''
try {
    if (-not ('System.IO.Compression.ZipFile' -as [type])) {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
    }

    if ($ProjectRootOverride) {
        $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRootOverride -ErrorAction Stop).Path
    }
    else {
        $ProjectRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot) -ErrorAction Stop).Path
    }
    $RuntimeParent = Join-Path $ProjectRoot 'runtime'
    $TargetRoot = Join-Path $ProjectRoot $QqTargetRelativePath
    $StagingRoot = Join-Path $RuntimeParent ('.qq-bootstrap-staging-' + $RunId)
    $BackupRoot = Join-Path $RuntimeParent ('.qq-bootstrap-backup-' + $RunId)

    $Pins = Get-QqRuntimePins
    Assert-OfficialUrl -Url ([string]$Pins.qce.archiveUrl) -AllowedHosts $OfficialArchiveHosts -Label 'qce.archiveUrl'
    Assert-OfficialUrl -Url ([string]$Pins.qce.releaseUrl) -AllowedHosts $OfficialArchiveHosts -Label 'qce.releaseUrl'

    New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null
    Write-Step "临时工作目录: $TempRoot"

    # 先完成全部来源校验，再替换目标：任何校验失败都不会改动 runtime\qq。
    $Archive = Get-QceArchive -Url ([string]$Pins.qce.archiveUrl)
    Assert-QceArchiveFile -ArchivePath $Archive -Pins $Pins
    Assert-QceArchiveEntries -ArchivePath $Archive -Pins $Pins
    $PreparedRoot = Expand-QceArchive -ArchivePath $Archive -Pins $Pins
    Remove-ExcludedRuntimeState -RuntimeRoot $PreparedRoot -Pins $Pins
    Update-LauncherUserBatch -RuntimeRoot $PreparedRoot -Pins $Pins
    Assert-PinnedRuntimeFiles -RuntimeRoot $PreparedRoot -Pins $Pins
    Assert-QqRuntimeContract -Root $PreparedRoot -Phase 'prepared'
    Assert-ExcludedRuntimeStateAbsent -RuntimeRoot $PreparedRoot -Pins $Pins -Label 'prepared runtime'

    Install-QqRuntime -PreparedRoot $PreparedRoot -RuntimeParent $RuntimeParent -TargetRoot $TargetRoot -StagingRoot $StagingRoot -BackupRoot $BackupRoot

    Assert-QqRuntimeContract -Root $TargetRoot -Phase 'installed'
    Assert-PinnedRuntimeFiles -RuntimeRoot $TargetRoot -Pins $Pins
    Assert-ExcludedRuntimeStateAbsent -RuntimeRoot $TargetRoot -Pins $Pins -Label 'runtime\qq'
    Assert-FileSha256 -Path (
        Join-Path $TargetRoot ((([string]$Pins.launcherPatch.path) -replace '/', '\'))
    ) -Expected ([string]$Pins.launcherPatch.patchedSha256) -Label 'runtime\qq\launcher-user.bat'
}
catch {
    $Failed = $true
    $FailureMessage = $_.Exception.Message
    if (-not $FailureMessage) {
        $FailureMessage = $_.Exception.GetType().FullName
    }
}
finally {
    # 备份只在目标已就位时丢弃；否则回滚，绝不留下一个被清空的目标。
    if ($BackupRoot -and (Test-Path -LiteralPath $BackupRoot)) {
        if ($TargetRoot -and (Test-Path -LiteralPath $TargetRoot)) {
            Remove-Item -LiteralPath $BackupRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
        else {
            Move-Item -LiteralPath $BackupRoot -Destination $TargetRoot -ErrorAction SilentlyContinue
        }
    }
    foreach ($Path in @($TempRoot, $StagingRoot)) {
        if ($Path -and (Test-Path -LiteralPath $Path)) {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
        }
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
Write-Host 'bootstrap_qq_runtime.ps1 完成。' -ForegroundColor Green
