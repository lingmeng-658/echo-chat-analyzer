#requires -Version 5.1
<#
.SYNOPSIS
  Zero-dependency WeChat WCDB diagnostic runner for a machine that only has the
  Echo distribution package (Windows PowerShell 5.1+, no dev toolchain needed).

.DESCRIPTION
  Directly invokes the bundled wcdb_cli.exe against the real session.db with the
  real key, captures stdout / stderr / exit code / last [wcdb-debug] stage, and
  writes a single redacted report (wcdb-diagnostic.txt). It intentionally does
  NOT go through the Python Provider so the raw helper output is preserved even
  when wcdb_cli.exe crashes natively (e.g. 0xC0000005 with empty stderr).

  Privacy guarantees:
  - The DbKey is only read from the environment (WX_DB_KEY, then ECHO_WX_DB_KEY)
    and is passed to wcdb_cli.exe through the WX_DB_KEY environment variable.
    It is never printed, never written to the report, and never put on the
    command line.
  - The report records only key presence / length / hex-format validity.
  - Text cells of query results (e.g. summary) are shown as [text:N chars];
    account-like identifiers are truncated to the first 12 characters.
  - No chat body, full account identifiers, tokens, cookies or passwords are
    written to the report.

.PARAMETER SessionDb
  Explicit path to session.db. When omitted the script searches Echo's known
  data locations (Documents\xwechat_files, Documents\WeChat Files, WeChat's
  configured storage parent) and asks for a path when the result is ambiguous.

.PARAMETER DataRoot
  Explicit WeChat data root directory to search instead of the defaults.

.PARAMETER EchoDir
  Root of the Echo distribution package (default: auto-detected next to the
  script). wcdb_cli.exe and WCDB.dll are expected under runtime\wechat.

.PARAMETER WcdbCli / WcdbDll
  Explicit helper executable / library paths (override auto-location).

.PARAMETER NoCipher
  Pass --no-cipher to wcdb_cli (development / plaintext database validation
  only; the real WeChat flow never uses this).

.PARAMETER ReportPath
  Where to write the report. Default: wcdb-diagnostic.txt next to this script
  (fallback: the current user's Desktop).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_wechat_wcdb_diagnostic.ps1

.OUTPUTS
  Exit codes:
    0 = both queries passed (ok:true, helper exit 0)
    1 = a query failed or crashed (report still written)
    2 = pre-flight failure (helper/dll/db/key missing) (report still written)
#>
[CmdletBinding()]
param(
    [string]$SessionDb,
    [string]$DataRoot,
    [string]$EchoDir,
    [string]$WcdbCli,
    [string]$WcdbDll,
    [switch]$NoCipher,
    [string]$ReportPath
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# SQL used by the real provider chain - keep verbatim (do not guess):
#   src/qq_chat_analyzer/providers/wechat_database_provider.py
#   list_sessions() builds: "SELECT username, summary, last_timestamp FROM
#   SessionTable ORDER BY last_timestamp DESC" (limit 200 via DEFAULT_SESSION_LIMIT).
$script:SessionListSql = 'SELECT username, summary, last_timestamp FROM SessionTable ORDER BY last_timestamp DESC'
$script:SessionListLimit = 200

$script:Report = New-Object System.Collections.Generic.List[string]
$script:ExitCode = 2
$script:CliPath = ''
$script:DllPath = ''
$script:DbPath = ''
$script:DbKey = ''
$script:ProbePassed = $false
$script:ProbeStage = 'none'
$script:ProbeExit = 0
$script:ProbeExitHex = '0x00000000'
$script:ListPassed = $false
$script:ListStage = 'none'
$script:ListExit = 0
$script:ListExitHex = '0x00000000'

function Write-ReportLine {
    param([string]$Line)
    $script:Report.Add($Line)
}

function Write-Diag {
    param([string]$Message)
    Write-Host "[diag] $Message"
}

function ConvertTo-RedactedText {
    param(
        [string]$Text,
        [string]$Secret
    )
    if (-not [string]::IsNullOrEmpty($Secret)) {
        $Text = $Text.Replace($Secret, '[REDACTED]')
    }
    return $Text
}

function ConvertTo-NativeArg {
    param([string]$Value)
    if ($Value -match '[\s"]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }
    return $Value
}

function Invoke-WcdbQuery {
    param(
        [string]$Sql,
        [int]$Limit,
        [string]$Label,
        [int]$TimeoutSeconds = 180
    )

    $argList = New-Object System.Collections.Generic.List[string]
    $argList.Add('--wcdb'); $argList.Add($script:DllPath)
    $argList.Add('--db');   $argList.Add($script:DbPath)
    $argList.Add('--sql');  $argList.Add($Sql)
    if ($Limit -gt 0) {
        $argList.Add('--limit'); $argList.Add([string]$Limit)
    }
    if ($script:NoCipher) {
        $argList.Add('--no-cipher')
    }

    $argumentString = (($argList | ForEach-Object { ConvertTo-NativeArg $_ }) -join ' ')
    Write-Verbose "invoking: $($script:CliPath) $argumentString"

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $script:CliPath
    $psi.Arguments = $argumentString
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true

    # Key travels through the parent process environment (never the command
    # line) and is restored afterwards. PS 5.1 ProcessStartInfo
    # EnvironmentVariables is not reliably available.
    $envKeyBackup = $env:WX_DB_KEY
    if (-not [string]::IsNullOrEmpty($script:DbKey)) {
        $env:WX_DB_KEY = $script:DbKey
    } else {
        Remove-Item Env:\WX_DB_KEY -ErrorAction SilentlyContinue
    }

    try {
        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $psi
        [void]$proc.Start()

        $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
        $stderrTask = $proc.StandardError.ReadToEndAsync()

        $timedOut = $false
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            $timedOut = $true
            try { $proc.Kill() } catch { }
            $proc.WaitForExit()
        } else {
            # Ensure async stream reads have flushed.
            $proc.WaitForExit()
        }

        $stdout = $stdoutTask.Result
        $stderr = $stderrTask.Result
    } finally {
        if ($null -eq $envKeyBackup) {
            Remove-Item Env:\WX_DB_KEY -ErrorAction SilentlyContinue
        } else {
            $env:WX_DB_KEY = $envKeyBackup
        }
    }
    # Windows exit codes are DWORDs; .NET exposes them as signed Int32 so a
    # native crash like 0xC0000005 arrives as -1073741819. Convert via the
    # byte representation to avoid PS 5.1 [uint32] cast failure on negatives.
    $exitCodeSigned = [int]$proc.ExitCode
    $exitCode = [BitConverter]::ToUInt32([BitConverter]::GetBytes($exitCodeSigned), 0)
    $exitHex = '0x{0:X8}' -f $exitCode

    $lastStage = 'none'
    $stageMatches = [regex]::Matches($stderr, '\[wcdb-debug\]\s+([A-Za-z][A-Za-z ]*)')
    if ($stageMatches.Count -gt 0) {
        $lastStage = $stageMatches[$stageMatches.Count - 1].Groups[1].Value.Trim()
    }

    $payload = $null
    $jsonError = ''
    try {
        $payload = $stdout | ConvertFrom-Json
    } catch {
        $jsonError = $_.Exception.Message
    }

    $ok = $false
    $rowCount = $null
    $truncatedFlag = $null
    if ($payload -ne $null) {
        $okProp = $payload.PSObject.Properties['ok']
        if ($okProp -ne $null) { $ok = ($okProp.Value -eq $true) }
        $rcProp = $payload.PSObject.Properties['row_count']
        if ($rcProp -ne $null) { $rowCount = $rcProp.Value }
        $trProp = $payload.PSObject.Properties['truncated']
        if ($trProp -ne $null) { $truncatedFlag = $trProp.Value }
    }

    Write-ReportLine '----------------------------------------------------------------'
    Write-ReportLine ("query: {0}" -f $Label)
    Write-ReportLine ("  sql={0}" -f $Sql)
    if ($Limit -gt 0) {
        Write-ReportLine ("  limit={0}" -f $Limit)
    }
    if ($timedOut) {
        Write-ReportLine ("  exit_code=timeout (>{0}s)" -f $TimeoutSeconds)
    } else {
        Write-ReportLine ("  exit_code={0} ({1})" -f $exitCode, $exitHex)
    }
    Write-ReportLine ("  last_wcdb_stage={0}" -f $lastStage)
    if ($payload -ne $null) {
        Write-ReportLine ("  ok={0} row_count={1} truncated={2}" -f $ok, $rowCount, $truncatedFlag)
    } elseif (-not [string]::IsNullOrEmpty($jsonError)) {
        Write-ReportLine ("  json_parse_error={0}" -f $jsonError)
    }

    if ($Label -eq 'minimal probe') {
        # sqlite_master result: table names only - safe to include verbatim.
        Write-ReportLine ('  stdout=' + (ConvertTo-RedactedText $stdout $script:DbKey).Trim())
    } else {
        # session_list rows may embed message previews - redact cell content.
        $rows = @()
        if ($payload -ne $null) {
            $rowsProp = $payload.PSObject.Properties['rows']
            if ($rowsProp -ne $null -and $rowsProp.Value -ne $null) { $rows = @($rowsProp.Value) }
        }
        $shown = 0
        foreach ($row in $rows) {
            if ($shown -ge 10) {
                $omitted = $rows.Count - 10
                if ($omitted -gt 0) { Write-ReportLine ("  ... {0} more row(s) omitted (report policy)" -f $omitted) }
                break
            }
            $parts = @()
            foreach ($prop in $row.PSObject.Properties) {
                $name = $prop.Name
                $value = $prop.Value
                if ($null -eq $value) {
                    $parts += "$name=null"
                } elseif ($value -is [bool] -or $value -is [int] -or $value -is [long] -or $value -is [double] -or $value -is [decimal]) {
                    $parts += "$name=$value"
                } elseif ($value -is [string]) {
                    if ($name -match 'user_name|username') {
                        $short = if ($value.Length -gt 12) { $value.Substring(0, 12) + '...' } else { $value }
                        $parts += "$name=$short"
                    } else {
                        $parts += "$name=[text:$($value.Length) chars]"
                    }
                } else {
                    $parts += "$name=[value]"
                }
            }
            Write-ReportLine ("  row{0} {{{1}}}" -f $shown, ($parts -join ', '))
            $shown++
        }
        if ($rows.Count -eq 0) {
            Write-ReportLine '  rows=[]'
        }
    }

    $stderrRedacted = (ConvertTo-RedactedText $stderr $script:DbKey).Trim()
    Write-ReportLine ('  stderr=' + ($(if ($stderrRedacted) { $stderrRedacted } else { '(empty)' })))

    $verdict = 'FAIL'
    if ($timedOut) {
        $verdict = 'TIMEOUT'
    } elseif ($ok -and ($exitCode -eq 0)) {
        $verdict = 'PASS'
    } elseif (($exitCode -eq 3221225477) -and ($payload -eq $null)) {
        $verdict = 'CRASH_ACCESS_VIOLATION'
    }
    Write-ReportLine ("  verdict={0}" -f $verdict)

    if ($Label -eq 'minimal probe') {
        $script:ProbePassed = ($verdict -eq 'PASS')
        $script:ProbeStage = $lastStage
        $script:ProbeExit = $exitCode
        $script:ProbeExitHex = $exitHex
    } else {
        $script:ListPassed = ($verdict -eq 'PASS')
        $script:ListStage = $lastStage
        $script:ListExit = $exitCode
        $script:ListExitHex = $exitHex
    }
}

function Resolve-WcdbPaths {
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($WcdbCli) { $candidates.Add($WcdbCli) }
    if ($EchoDir) { $candidates.Add((Join-Path $EchoDir 'runtime\wechat\wcdb_cli.exe')) }
    if ($PSScriptRoot) {
        $candidates.Add((Join-Path $PSScriptRoot '..\dist\Echo\runtime\wechat\wcdb_cli.exe'))
        $candidates.Add((Join-Path $PSScriptRoot '..\runtime\wechat\wcdb_cli.exe'))
        $candidates.Add((Join-Path $PSScriptRoot 'runtime\wechat\wcdb_cli.exe'))
    }

    $cli = $null
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $cli = (Resolve-Path -LiteralPath $candidate).Path
            break
        }
    }
    if (-not $cli) {
        throw 'wcdb_cli.exe not found. Pass -WcdbCli or -EchoDir, or place the script next to the Echo package.'
    }

    if ($WcdbDll) {
        if (-not (Test-Path -LiteralPath $WcdbDll -PathType Leaf)) {
            throw "WCDB.dll not found at: $WcdbDll"
        }
        $dll = (Resolve-Path -LiteralPath $WcdbDll).Path
    } else {
        # The helper imports WCDB.dll by name, so the DLL must sit next to the exe.
        $dllCandidate = Join-Path (Split-Path -Parent $cli) 'WCDB.dll'
        if (-not (Test-Path -LiteralPath $dllCandidate -PathType Leaf)) {
            throw "WCDB.dll not found next to the helper: $dllCandidate"
        }
        $dll = (Resolve-Path -LiteralPath $dllCandidate).Path
    }

    $script:CliPath = $cli
    $script:DllPath = $dll
    Write-Diag "wcdb_cli: $cli"
    Write-Diag "WCDB.dll: $dll"
}

function Get-SessionDbCandidates {
    param([string[]]$BaseDirs)
    $found = New-Object System.Collections.Generic.List[string]
    foreach ($base in $BaseDirs) {
        if (-not (Test-Path -LiteralPath $base -PathType Container)) {
            continue
        }
        $root = (Resolve-Path -LiteralPath $base).Path
        # Direct hit at the root.
        $direct = Join-Path $root 'session.db'
        if (Test-Path -LiteralPath $direct -PathType Leaf) {
            $found.Add((Resolve-Path -LiteralPath $direct).Path)
        }
        # db_storage directories (mirrors _iter_db_directories) plus their
        # immediate children; bounded recursion to avoid a broad disk scan.
        $storageDirs = Get-ChildItem -LiteralPath $root -Directory -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq 'db_storage' } |
            Select-Object -First 50
        foreach ($storage in $storageDirs) {
            $db = Join-Path $storage.FullName 'session.db'
            if (Test-Path -LiteralPath $db -PathType Leaf) {
                $found.Add((Resolve-Path -LiteralPath $db).Path)
            }
            foreach ($child in @(Get-ChildItem -LiteralPath $storage.FullName -Directory -ErrorAction SilentlyContinue)) {
                $childDb = Join-Path $child.FullName 'session.db'
                if (Test-Path -LiteralPath $childDb -PathType Leaf) {
                    $found.Add((Resolve-Path -LiteralPath $childDb).Path)
                }
            }
        }
    }
    return @($found | Select-Object -Unique)
}

function Resolve-SessionDb {
    if ($SessionDb) {
        if (-not (Test-Path -LiteralPath $SessionDb -PathType Leaf)) {
            throw "session.db not found at: $SessionDb"
        }
        $script:DbPath = (Resolve-Path -LiteralPath $SessionDb).Path
        return
    }

    $baseDirs = New-Object System.Collections.Generic.List[string]
    if ($DataRoot) {
        $baseDirs.Add($DataRoot)
    } else {
        $home = [Environment]::GetFolderPath('UserProfile')
        $baseDirs.Add((Join-Path $home 'Documents\xwechat_files'))
        $baseDirs.Add((Join-Path $home 'Documents\WeChat Files'))

        # WeChat's persisted custom storage parents (same sources as Echo's
        # wechat_data_detector): %APPDATA% ini files and HKCU registry.
        $appdata = [Environment]::GetFolderPath('ApplicationData')
        foreach ($ini in @(Get-ChildItem -LiteralPath (Join-Path $appdata 'Tencent\xwechat\config') -Filter *.ini -ErrorAction SilentlyContinue)) {
            $line = Get-Content -LiteralPath $ini.FullName -Raw -ErrorAction SilentlyContinue
            if ($line -and $line.Trim()) {
                $baseDirs.Add($line.Trim())
            }
        }
        foreach ($ini in @(Get-ChildItem -LiteralPath (Join-Path $appdata 'Tencent\WeChat\All Users\config') -Filter *.ini -ErrorAction SilentlyContinue)) {
            foreach ($rawLine in @(Get-Content -LiteralPath $ini.FullName -ErrorAction SilentlyContinue)) {
                if ($rawLine -match '^\s*FileSavePath\s*=\s*(.+)\s*$') {
                    $baseDirs.Add($Matches[1].Trim())
                }
            }
        }
        try {
            $regValue = (Get-ItemProperty -LiteralPath 'HKCU:\Software\Tencent\WeChat' -Name FileSavePath -ErrorAction Stop).FileSavePath
            if ($regValue) {
                $baseDirs.Add([string]$regValue)
            }
        } catch {
            # registry key absent - ignore
        }
    }

    $candidates = Get-SessionDbCandidates -BaseDirs $baseDirs.ToArray()
    if ($candidates.Count -eq 1) {
        $script:DbPath = $candidates[0]
        return
    }
    if ($candidates.Count -eq 0) {
        Write-Diag 'No session.db found in Echo known locations.'
    } else {
        Write-Diag ("Found {0} session.db candidates:" -f $candidates.Count)
        foreach ($candidate in $candidates) {
            Write-Diag "  $candidate"
        }
    }
    $prompt = Read-Host 'Enter the exact path to session.db (or leave empty to abort)'
    if ([string]::IsNullOrWhiteSpace($prompt)) {
        throw 'No session.db selected.'
    }
    if (-not (Test-Path -LiteralPath $prompt -PathType Leaf)) {
        throw "session.db not found at: $prompt"
    }
    $script:DbPath = (Resolve-Path -LiteralPath $prompt).Path
}

function Resolve-DbKey {
    if ($script:NoCipher) {
        Write-ReportLine '  key_required=false (--no-cipher)'
        return
    }
    $key = $env:WX_DB_KEY
    if ([string]::IsNullOrWhiteSpace($key)) {
        $key = $env:ECHO_WX_DB_KEY
    }
    if ([string]::IsNullOrWhiteSpace($key)) {
        Write-ReportLine '  key_present=no'
        throw 'No DbKey available. Set WX_DB_KEY or ECHO_WX_DB_KEY to the 64-hex key and rerun.'
    }
    $key = $key.Trim()
    $keyValid = ($key -match '^[0-9a-fA-F]{64}$')
    Write-ReportLine ("  key_present=yes key_length={0} key_format_valid={1}" -f $key.Length, $keyValid)
    if (-not $keyValid) {
        throw 'DbKey format invalid (expected exactly 64 hex characters).'
    }
    $script:DbKey = $key
}

# ------------------------------------------------------------------ main
try {
    $now = Get-Date
    Write-ReportLine '================================================================'
    Write-ReportLine ' Echo wcdb_cli diagnostic report'
    Write-ReportLine (" generated_at={0:yyyy-MM-ddTHH:mm:ss}" -f $now)
    Write-ReportLine (" host_os={0}" -f [System.Environment]::OSVersion.VersionString)
    Write-ReportLine (" host_arch={0}" -f $env:PROCESSOR_ARCHITECTURE)
    Write-ReportLine '----------------------------------------------------------------'

    Resolve-WcdbPaths

    Write-ReportLine '----------------------------------------------------------------'
    Write-ReportLine ' locate'
    Write-ReportLine ("  wcdb_cli={0}" -f $script:CliPath)
    Write-ReportLine ("  wcdb_dll={0}" -f $script:DllPath)

    Resolve-SessionDb
    Write-ReportLine ("  session_db={0}" -f $script:DbPath)

    Resolve-DbKey
    $script:ExitCode = 1

    Write-ReportLine '----------------------------------------------------------------'
    Write-ReportLine ' queries'
    Invoke-WcdbQuery -Sql 'SELECT count(*) FROM sqlite_master' -Limit 0 -Label 'minimal probe'
    Invoke-WcdbQuery -Sql $script:SessionListSql -Limit $script:SessionListLimit -Label 'session_list (real SQL)'

    Write-ReportLine '----------------------------------------------------------------'
    if ($script:ProbePassed -and $script:ListPassed) {
        $script:ExitCode = 0
        Write-ReportLine ' summary: PASS - minimal probe and session_list both succeeded'
    } elseif (-not $script:ProbePassed) {
        Write-ReportLine (" summary: FAIL - minimal probe failed (exit {0} {1}, last stage {2})" -f $script:ProbeExit, $script:ProbeExitHex, $script:ProbeStage)
    } else {
        Write-ReportLine (" summary: FAIL - count(*) ok but session_list failed (exit {0} {1}, last stage {2})" -f $script:ListExit, $script:ListExitHex, $script:ListStage)
    }
} catch {
    $script:ExitCode = 2
    Write-ReportLine '----------------------------------------------------------------'
    Write-ReportLine (" error: {0}" -f $_.Exception.Message)
} finally {
    Write-ReportLine '================================================================'

    if ($ReportPath) {
        $finalReport = $ReportPath
    } elseif ($PSScriptRoot) {
        $finalReport = Join-Path $PSScriptRoot 'wcdb-diagnostic.txt'
    } else {
        $finalReport = Join-Path ([Environment]::GetFolderPath('Desktop')) 'wcdb-diagnostic.txt'
    }
    $reportDir = Split-Path -Parent $finalReport
    if (-not (Test-Path -LiteralPath $reportDir -PathType Container)) {
        New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
    }
    $script:Report | Set-Content -LiteralPath $finalReport -Encoding UTF8
    Write-Diag "report written: $finalReport"
    Write-Diag "exit code: $script:ExitCode"
}

exit $script:ExitCode
