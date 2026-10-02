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

# The portable runtime contract lives in one tracked manifest so the build and
# the tests can never drift into two hand-maintained required-asset lists.
# It sits next to this script and also pins the machine-local state that must
# never ship, so it is resolved from the script location rather than from the
# (possibly overridden) project root.
$RuntimeContractPath = Join-Path $PSScriptRoot "windows_runtime_manifest.json"
$RuntimeContract = $null
$QQConfigSeeds = @()

function Get-RuntimeContract {
    if ($null -ne $RuntimeContract) {
        return $RuntimeContract
    }
    if (-not (Test-Path -LiteralPath $RuntimeContractPath -PathType Leaf)) {
        throw "Runtime contract manifest is missing: scripts\windows_runtime_manifest.json"
    }
    $Contract = (
        Get-Content -LiteralPath $RuntimeContractPath -Raw -Encoding UTF8
    ) | ConvertFrom-Json
    if (-not $Contract.requirements -or -not $Contract.privatePaths -or -not $Contract.packageDirectories) {
        throw "Runtime contract manifest is incomplete: scripts\windows_runtime_manifest.json"
    }
    $script:RuntimeContract = $Contract
    return $script:RuntimeContract
}

function Get-QQConfigSeedRequirement {
    return @(
        (Get-RuntimeContract).requirements | Where-Object {
            [string]$_.source -eq "qq" -and
            ([string]$_.path) -like "qq/config/*" -and
            [string]$_.type -eq "file"
        }
    )
}

function Assert-RuntimeContract {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [ValidateSet("source", "portable")]
        [string]$Phase
    )

    $MissingMessage = if ($Phase -eq "source") {
        "Required runtime resource is missing"
    }
    else {
        "Portable runtime copy is incomplete"
    }
    $EmptyMessage = if ($Phase -eq "source") {
        "Required runtime directory is empty"
    }
    else {
        "Portable runtime directory is empty"
    }

    foreach ($Requirement in (Get-RuntimeContract).requirements) {
        $RelativePath = ([string]$Requirement.path) -replace '/', '\'
        $Target = Join-Path $Root $RelativePath
        switch ([string]$Requirement.type) {
            "file" {
                if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
                    throw ($MissingMessage + ": runtime\" + $RelativePath)
                }
            }
            "non-empty-directory" {
                if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
                    throw ($MissingMessage + ": runtime\" + $RelativePath)
                }
                if (@(Get-ChildItem -LiteralPath $Target -Force).Count -eq 0) {
                    throw ($EmptyMessage + ": runtime\" + $RelativePath)
                }
            }
            default {
                throw (
                    "Unknown runtime contract requirement type '" +
                    [string]$Requirement.type + "': runtime\" + $RelativePath
                )
            }
        }
    }
}

function Assert-PrivateRuntimeStateAbsent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    foreach ($Entry in (Get-RuntimeContract).privatePaths) {
        $RelativePath = ([string]$Entry.path) -replace '/', '\'
        $Target = Join-Path $Root $RelativePath
        if (Test-Path -LiteralPath $Target) {
            throw ($Label + ": runtime\" + $RelativePath)
        }
    }
}

function Test-MutableRuntimePath([string]$RelativePath) {
    # One policy for state accidentally placed inside an allowed program tree.
    # Static auth/sessions folders are frontend routes, not user state.
    $Parts = $RelativePath.ToLowerInvariant() -split '/'
    $Directories = @('output', 'logs', 'cache', 'temp', 'tmp', 'staging',
        'generations', 'decrypted', 'scratch', 'data', 'reports', '.codex',
        'session', 'sessions', 'auth')
    for ($Index = 0; $Index -lt $Parts.Count - 1; $Index++) {
        if ($Parts[$Index] -in $Directories) {
            if ($RelativePath -like 'qq/static/qce/*' -and
                $Index -eq 3 -and $Parts[$Index] -in @('auth', 'sessions')) { continue }
            return $true
        }
    }
    $Name = $Parts[-1]
    return ($Name -match '\.(?:db(?:-(?:wal|shm|journal))?|sqlite(?:3)?|jsonl|log)$' -or
        $Name -eq '.env' -or
        $Name -match '^(?:token|key|cookie|password|passphrase|credentials|security|session|auth|account)(?:[._-].*)?\.(?:json|txt|ini|env)$')
}

function Assert-ProgramPathNotLinked([string]$Path) {
    $Current = [IO.Path]::GetFullPath($Path)
    while ($Current) {
        if ((Get-Item -LiteralPath $Current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Runtime program asset is a reparse point; refusing to package it.'
        }
        $Parent = Split-Path -Parent $Current
        if ($Parent -eq $Current) { break }
        $Current = $Parent
    }
}

function Copy-RuntimeProgramAssets([string]$SourceRoot, [string]$DestinationRoot) {
    # requirements is a presence contract, not permission to copy broad roots
    # such as qq/plugins. Only its explicit files and packageDirectories ship.
    $Files = @{}
    $Contract = Get-RuntimeContract
    foreach ($Entry in @($Contract.requirements | Where-Object { $_.type -eq 'file' }) +
        @($Contract.packageDirectories)) {
        $Relative = [string]$Entry.path
        if ($Relative -match '(^/|\\|:|(^|/)\.\.(/|$))' -or
            -not $Relative.StartsWith(([string]$Entry.source + '/'))) {
            throw 'Invalid runtime program asset path in manifest.'
        }
        $Source = Join-Path $SourceRoot $Relative
        Assert-ProgramPathNotLinked $Source
        if ([string]$Entry.type -eq 'file') {
            if (Test-MutableRuntimePath $Relative) { throw 'Manifest names a mutable runtime asset.' }
            $Files[$Relative] = $Source
        }
        elseif ([string]$Entry.type -eq 'directory') {
            $Pending = [Collections.Generic.Stack[string]]::new()
            $Pending.Push($Source)
            while ($Pending.Count) {
                foreach ($Child in Get-ChildItem -LiteralPath $Pending.Pop() -Force) {
                    if ($Child.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                        throw 'Runtime program asset is a reparse point; refusing to package it.'
                    }
                    $ChildRelative = $Child.FullName.Substring($SourceRoot.Length + 1) -replace '\\', '/'
                    $PolicyPath = if ($Child.PSIsContainer) { $ChildRelative + '/entry' } else { $ChildRelative }
                    if (Test-MutableRuntimePath $PolicyPath) { continue }
                    if ($Child.PSIsContainer) { $Pending.Push($Child.FullName) }
                    else { $Files[$ChildRelative] = $Child.FullName }
                }
            }
        }
        else { throw 'Invalid runtime program asset type in manifest.' }
    }
    # Enumerate and validate before copying; never visit the live output tree.
    foreach ($Relative in $Files.Keys) {
        $Destination = Join-Path $DestinationRoot $Relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Copy-Item -LiteralPath $Files[$Relative] -Destination $Destination
    }
}

# NapCat bundles native addons for every Node.js platform/arch pair it supports
# and selects exactly one variant at runtime via
# `process.platform + "." + process.arch` (native\ffmpeg, native\napi2native,
# native\packet, native\pty, native\dpapi). This distribution targets Windows
# x64, so only the win32.x64 addons can ever be loaded and the packaged copy
# drops the foreign platform/arch variants. The repository runtime directory
# stays complete as the upstream source of truth.
#
# The pattern matches a single path segment carrying a foreign platform
# designator (native\pty\linux.x64, native\dpapi\win32-arm64) or a foreign
# architecture designator for an x64-only distribution
# (MoeHoo.linux.arm64.node). Segments carrying neither designator, such as
# native\napi2native\ffmpeg.dll, are kept.
$ForeignNativeSegmentPattern = '(^|[.\-_])(linux|darwin|freebsd|openbsd|netbsd|sunos|aix|android|arm64)([.\-_]|$)'

function Remove-ForeignQQNativeAssets {
    param(
        [Parameter(Mandatory = $true)]
        [string]$NativeRoot,
        [Parameter(Mandatory = $true)]
        [string]$ForeignSegmentPattern
    )

    if (-not (Test-Path -LiteralPath $NativeRoot -PathType Container)) {
        return
    }

    $ForeignFiles = @(
        Get-ChildItem -LiteralPath $NativeRoot -Recurse -File -Force |
            Where-Object {
                $Segments = $_.FullName.Substring($NativeRoot.Length) -split '[\\/]'
                @($Segments | Where-Object {
                        $_ -match $ForeignSegmentPattern
                    }).Count -gt 0
            }
    )
    foreach ($ForeignFile in $ForeignFiles) {
        Remove-Item -LiteralPath $ForeignFile.FullName -Force
    }

    # Foreign-only directories (native\pty\linux.x64, native\dpapi\win32-arm64)
    # are left behind as empty shells once their payload is gone.
    $ForeignDirectories = @(
        Get-ChildItem -LiteralPath $NativeRoot -Recurse -Directory -Force |
            Sort-Object { $_.FullName.Length } -Descending |
            Where-Object { $_.Name -match $ForeignSegmentPattern }
    )
    foreach ($ForeignDirectory in $ForeignDirectories) {
        if (@(Get-ChildItem -LiteralPath $ForeignDirectory.FullName -Force).Count -eq 0) {
            Remove-Item -LiteralPath $ForeignDirectory.FullName -Force
        }
    }
}

if (-not (Test-Path -LiteralPath $RuntimeSource -PathType Container)) {
    throw "Runtime source directory is missing. Restore the repository runtime directory before building."
}

# Validate the contract before packaging starts: a package that would be
# missing a product dependency must never be produced.
Assert-RuntimeContract -Root $RuntimeSource -Phase "source"
$QQConfigSeeds = Get-QQConfigSeedRequirement

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
    Copy-RuntimeProgramAssets -SourceRoot $RuntimeSource -DestinationRoot $PortableRuntime

    # Ship only the native addons this Windows x64 distribution loads; see the
    # pruning policy above.
    Remove-ForeignQQNativeAssets -NativeRoot (
        Join-Path $PortableRuntime "qq\native"
    ) -ForeignSegmentPattern $ForeignNativeSegmentPattern

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

    # loadNapCat.js is rewritten by the launcher on every start and embeds the
    # absolute runtime folder of whichever machine generated it.
    $GeneratedLoader = Join-Path $PortableRuntime "qq\loadNapCat.js"
    if (Test-Path -LiteralPath $GeneratedLoader) {
        Remove-Item -LiteralPath $GeneratedLoader -Force
    }

    # Restore only the machine-independent config files the contract requires.
    # Everything else under qq\config stays excluded, so a purge followed by an
    # explicit re-copy can never leak a saved path or a per-install file.
    foreach ($Seed in $QQConfigSeeds) {
        $SeedRelativePath = ([string]$Seed.path) -replace '/', '\'
        $SeedDestination = Join-Path $PortableRuntime $SeedRelativePath
        New-Item -ItemType Directory -Force -Path (
            Split-Path -Parent $SeedDestination
        ) | Out-Null
        Copy-Item -LiteralPath (
            Join-Path $RuntimeSource $SeedRelativePath
        ) -Destination $SeedDestination -Force
    }

    Assert-RuntimeContract -Root $PortableRuntime -Phase "portable"
    Assert-PrivateRuntimeStateAbsent -Root $PortableRuntime -Label (
        "Portable runtime contains state that must never ship"
    )
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
