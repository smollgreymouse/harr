[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$Start,
    [switch]$HarrOnly,
    [switch]$NoPathUpdate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $SourceDir
$CommonSource = Join-Path $RepoRoot 'common'
$FilesSource = Join-Path $SourceDir 'files'
$UserHome = if ($env:HARR_HOME) { $env:HARR_HOME } elseif ($env:USERPROFILE) { $env:USERPROFILE } else { [Environment]::GetFolderPath('UserProfile') }
$LocalRoot = if ($env:HARR_LOCALAPPDATA) { $env:HARR_LOCALAPPDATA } elseif ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $UserHome 'AppData\Local' }
$HarrRoot = Join-Path $LocalRoot 'Harr'
$BinDir = Join-Path $HarrRoot 'bin'
$LibExecDir = Join-Path $HarrRoot 'libexec'
$StateRoot = Join-Path $LocalRoot 'HarrState'
$StateHelperSource = Join-Path $FilesSource 'state\harr-state.ps1'
$StateHelper = Join-Path $StateRoot 'harr-state.ps1'
$CleanMarker = Join-Path $StateRoot 'pre-harr\complete'
$env:HARR_MCP_REGISTRY = Join-Path $CommonSource 'mcp\registry.json'

function Write-Utf8([string]$Path, [string]$Value) {
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    [IO.File]::WriteAllText($Path, $Value, (New-Object Text.UTF8Encoding($false)))
}

function Copy-TreeFresh([string]$Source, [string]$Target) {
    if (Test-Path -LiteralPath $Target) { Remove-Item -LiteralPath $Target -Recurse -Force }
    $parent = Split-Path -Parent $Target
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Target -Recurse -Force
}

if ($env:OS -ne 'Windows_NT') { throw 'install.ps1 is the Windows Harr installer' }
if (-not (Test-Path $StateHelperSource)) { throw "Missing Harr state helper: $StateHelperSource" }
if (-not (Get-Command python.exe -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Get-Command py.exe -ErrorAction SilentlyContinue)) {
    throw 'Python 3 is required for Harr host configuration management'
}

if (-not (Test-Path $CleanMarker) -and -not $Clean) {
    throw 'First Harr installation requires -Clean; Harr will not merge itself into an existing global harness'
}
if ((Test-Path $CleanMarker) -and $Clean) {
    Write-Host 'Clean ownership already initialized; preserving original pre-Harr snapshot.'
}
# Run on every install: existing clean snapshots are extended only for newly
# introduced registry service task names, before Harr can overwrite them.
& $StateHelperSource snapshot

New-Item -ItemType Directory -Force -Path $BinDir, $LibExecDir, $StateRoot | Out-Null
Copy-Item -LiteralPath $StateHelperSource -Destination $StateHelper -Force
Copy-TreeFresh $CommonSource (Join-Path $LibExecDir 'common')
Copy-TreeFresh $FilesSource (Join-Path $LibExecDir 'windows\files')
Copy-Item -LiteralPath (Join-Path $SourceDir 'harr.ps1') -Destination (Join-Path $LibExecDir 'harr.ps1') -Force

$harrCmd = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $LibExecDir 'harr.ps1')`" %*`r`n"
Write-Utf8 (Join-Path $BinDir 'harr.cmd') $harrCmd
$runner = Join-Path $LibExecDir 'windows\files\mcp\harr-mcp-run.ps1'
$runnerCmd = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$runner`" %*`r`n"
Write-Utf8 (Join-Path $BinDir 'harr-mcp-run.cmd') $runnerCmd

if (-not $NoPathUpdate) {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @()
    if ($userPath) { $parts = @($userPath.Split(';') | Where-Object { $_ }) }
    if (-not ($parts | Where-Object { $_.TrimEnd('\') -ieq $BinDir.TrimEnd('\') })) {
        $newPath = if ($userPath) { "$userPath;$BinDir" } else { $BinDir }
        [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    }
}
$env:Path = "$BinDir;$env:Path"

$installedHarr = Join-Path $LibExecDir 'harr.ps1'
if ($HarrOnly) {
    & $installedHarr registry apply
    & $installedHarr hosts apply
    & $installedHarr agents apply all
    & $installedHarr leanctx apply
} else {
    & $installedHarr install all
}

if ($Start -and -not $HarrOnly) {
    & $installedHarr mcp restart all
}

Write-Host ''
Write-Host 'Harr installed in clean global-harness mode for Windows.'
Write-Host "CLI: $(Join-Path $BinDir 'harr.cmd')"
Write-Host 'Project-level configs/files were not touched.'
Write-Host "MCP registry: $(Join-Path $LibExecDir 'common\mcp\registry.json')"
if ($HarrOnly) {
    Write-Host 'Stack components were skipped (-HarrOnly). Install later with: harr install all'
} else {
    Write-Host 'Pinned stack installed; LeanCTX registered in Codex/OpenCode; global agent policy applied.'
}
Write-Host 'Open a new terminal after installation if the harr command is not yet visible.'
Write-Host 'Check with: harr status'
Write-Host 'Rollback completely with: harr uninstall'
