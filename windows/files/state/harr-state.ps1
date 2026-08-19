[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('snapshot', 'safety-snapshot', 'restore', 'status')]
    [string]$Command = 'status'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$UserHome = if ($env:HARR_HOME) { $env:HARR_HOME } elseif ($env:USERPROFILE) { $env:USERPROFILE } else { [Environment]::GetFolderPath('UserProfile') }
$LocalRoot = if ($env:HARR_LOCALAPPDATA) { $env:HARR_LOCALAPPDATA } elseif ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $UserHome 'AppData\Local' }
$ConfigHome = if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { Join-Path $UserHome '.config' }
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $UserHome '.codex' }
$OpenCodeHome = Join-Path $ConfigHome 'opencode'
$StateRoot = Join-Path $LocalRoot 'HarrState'
$PreHarr = Join-Path $StateRoot 'pre-harr'
$BackupRoot = Join-Path $LocalRoot 'HarrUninstallBackups'
$InstalledRegistry = Join-Path $LocalRoot 'Harr\libexec\common\mcp\registry.json'
$Registry = if ($env:HARR_MCP_REGISTRY) { $env:HARR_MCP_REGISTRY } else { $InstalledRegistry }
$LegacyTaskName = 'Harr GitLab MCP'

$Items = [ordered]@{
    'codex-agents' = Join-Path $CodexHome 'AGENTS.md'
    'codex-config' = Join-Path $CodexHome 'config.toml'
    'opencode-agents' = Join-Path $OpenCodeHome 'AGENTS.md'
    'opencode-jsonc' = Join-Path $OpenCodeHome 'opencode.jsonc'
    'opencode-json' = Join-Path $OpenCodeHome 'opencode.json'
    'codex-skill-harr' = Join-Path $CodexHome 'skills\harr'
    'codex-skill-leanctx' = Join-Path $CodexHome 'skills\lean-ctx'
    'opencode-skill-harr' = Join-Path $OpenCodeHome 'skills\harr'
    'opencode-skill-leanctx' = Join-Path $OpenCodeHome 'skills\lean-ctx'
    'leanctx-config' = Join-Path $ConfigHome 'lean-ctx\config.toml'
    'ocwf-command-build-log' = Join-Path $OpenCodeHome 'commands\build-log.md'
    'ocwf-command-build-ok' = Join-Path $OpenCodeHome 'commands\build-ok.md'
    'ocwf-command-quick' = Join-Path $OpenCodeHome 'commands\quick.md'
    'ocwf-command-review' = Join-Path $OpenCodeHome 'commands\review.md'
    'ocwf-command-safe' = Join-Path $OpenCodeHome 'commands\safe.md'
    'ocwf-command-validate' = Join-Path $OpenCodeHome 'commands\validate.md'
    'harr-root' = Join-Path $LocalRoot 'Harr'
}

function Write-Utf8([string]$Path, [string]$Value) {
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    [IO.File]::WriteAllText($Path, $Value, (New-Object Text.UTF8Encoding($false)))
}

function Snapshot-Item([string]$Root, [string]$Name, [string]$Target) {
    $dir = Join-Path (Join-Path $Root 'items') $Name
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Write-Utf8 (Join-Path $dir 'target.txt') $Target
    $payload = Join-Path $dir 'payload'
    if (Test-Path -LiteralPath $payload) { Remove-Item -LiteralPath $payload -Recurse -Force }
    if (Test-Path -LiteralPath $Target) {
        Write-Utf8 (Join-Path $dir 'existed.txt') '1'
        Copy-Item -LiteralPath $Target -Destination $payload -Recurse -Force
    } else {
        Write-Utf8 (Join-Path $dir 'existed.txt') '0'
    }
}

function Snapshot-UserPath([string]$Root) {
    $value = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($null -eq $value) {
        Write-Utf8 (Join-Path $Root 'user-path-existed.txt') '0'
    } else {
        Write-Utf8 (Join-Path $Root 'user-path-existed.txt') '1'
        Write-Utf8 (Join-Path $Root 'user-path.txt') $value
    }
}

function Registry-ServiceTaskNames {
    if (-not (Test-Path -LiteralPath $Registry)) { return [string[]]@() }
    $data = Get-Content -Raw -LiteralPath $Registry | ConvertFrom-Json
    [string[]]$names = @()
    foreach ($server in @($data.servers)) {
        if ($server.lifecycle -ne 'service') { continue }
        $task = $null
        if ($server.PSObject.Properties.Name -contains 'windows_task') { $task = [string]$server.windows_task }
        if (-not $task) { $task = "Harr MCP $($server.name)" }
        $names += $task
    }
    return [string[]]@($names | Select-Object -Unique)
}

function Task-Key([string]$Name) {
    $bytes = [Text.Encoding]::UTF8.GetBytes($Name)
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
}

function Task-SnapshotDir([string]$Root, [string]$Name) {
    return Join-Path (Join-Path $Root 'tasks') (Task-Key $Name)
}

function Snapshot-TaskNamed([string]$Root, [string]$Name) {
    $dir = Task-SnapshotDir $Root $Name
    if (Test-Path -LiteralPath (Join-Path $dir 'name.txt')) { return }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Write-Utf8 (Join-Path $dir 'name.txt') $Name
    $present = $false
    if (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue) {
        try {
            [void](Get-ScheduledTask -TaskName $Name -ErrorAction Stop)
            $xml = Export-ScheduledTask -TaskName $Name -ErrorAction Stop
            Write-Utf8 (Join-Path $dir 'task.xml') $xml
            $present = $true
        } catch { }
    }
    Write-Utf8 (Join-Path $dir 'existed.txt') ($(if ($present) { '1' } else { '0' }))
}

function Migrate-LegacyTaskSnapshot([string]$Root) {
    $oldExists = Join-Path $Root 'task-existed.txt'
    if (-not (Test-Path -LiteralPath $oldExists)) { return }
    $dir = Task-SnapshotDir $Root $LegacyTaskName
    if (Test-Path -LiteralPath (Join-Path $dir 'name.txt')) { return }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Write-Utf8 (Join-Path $dir 'name.txt') $LegacyTaskName
    Copy-Item -LiteralPath $oldExists -Destination (Join-Path $dir 'existed.txt') -Force
    $oldXml = Join-Path $Root 'task.xml'
    if (Test-Path -LiteralPath $oldXml) { Copy-Item -LiteralPath $oldXml -Destination (Join-Path $dir 'task.xml') -Force }
}

function Snapshot-RegistryTasks([string]$Root) {
    Migrate-LegacyTaskSnapshot $Root
    foreach ($name in @(Registry-ServiceTaskNames)) { Snapshot-TaskNamed $Root $name }
}

function Snapshot-All([string]$Root) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Root 'items') | Out-Null
    foreach ($entry in $Items.GetEnumerator()) { Snapshot-Item $Root $entry.Key $entry.Value }
    Snapshot-UserPath $Root
    Snapshot-RegistryTasks $Root
    Write-Utf8 (Join-Path $Root 'complete') 'ok'
}

function Restore-Item([string]$Root, [string]$Name) {
    $dir = Join-Path (Join-Path $Root 'items') $Name
    $targetFile = Join-Path $dir 'target.txt'
    $existedFile = Join-Path $dir 'existed.txt'
    if (-not (Test-Path -LiteralPath $targetFile) -or -not (Test-Path -LiteralPath $existedFile)) { return }
    $target = (Get-Content -Raw -LiteralPath $targetFile).TrimEnd("`r", "`n")
    $existed = (Get-Content -Raw -LiteralPath $existedFile).Trim()
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    if ($existed -eq '1') {
        $parent = Split-Path -Parent $target
        if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        Copy-Item -LiteralPath (Join-Path $dir 'payload') -Destination $target -Recurse -Force
        Write-Host "Restored $target"
    } else {
        Write-Host "Removed Harr-created $target"
    }
}

function Restore-UserPath([string]$Root) {
    $existsFile = Join-Path $Root 'user-path-existed.txt'
    if (-not (Test-Path $existsFile)) { return }
    if ((Get-Content -Raw $existsFile).Trim() -eq '1') {
        $value = Get-Content -Raw (Join-Path $Root 'user-path.txt')
        [Environment]::SetEnvironmentVariable('Path', $value, 'User')
    } else {
        [Environment]::SetEnvironmentVariable('Path', $null, 'User')
    }
}

function Snapshot-TaskNames([string]$Root) {
    $tasksRoot = Join-Path $Root 'tasks'
    if (-not (Test-Path -LiteralPath $tasksRoot)) { return [string[]]@() }
    [string[]]$names = @()
    foreach ($dir in @(Get-ChildItem -LiteralPath $tasksRoot -Directory -ErrorAction SilentlyContinue)) {
        $nameFile = Join-Path $dir.FullName 'name.txt'
        if (Test-Path -LiteralPath $nameFile) { $names += (Get-Content -Raw -LiteralPath $nameFile).TrimEnd("`r","`n") }
    }
    return [string[]]$names
}

function Restore-RegistryTasks([string]$Root) {
    if (-not (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue)) { return }
    Migrate-LegacyTaskSnapshot $Root
    [string[]]$names = @((Registry-ServiceTaskNames) + (Snapshot-TaskNames $Root) | Select-Object -Unique)
    foreach ($name in $names) {
        try { Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue } catch { }
    }
    foreach ($name in @(Snapshot-TaskNames $Root)) {
        $dir = Task-SnapshotDir $Root $name
        $existed = (Get-Content -Raw -LiteralPath (Join-Path $dir 'existed.txt')).Trim()
        if ($existed -eq '1') {
            $xml = Get-Content -Raw -LiteralPath (Join-Path $dir 'task.xml')
            Register-ScheduledTask -TaskName $name -Xml $xml -Force | Out-Null
            Write-Host "Restored scheduled task $name"
        }
    }
}

switch ($Command) {
    'snapshot' {
        if (Test-Path (Join-Path $PreHarr 'complete')) {
            Snapshot-RegistryTasks $PreHarr
            Write-Host "Pre-Harr snapshot already exists and registry task ownership is current: $PreHarr"
            exit 0
        }
        $tmp = Join-Path $StateRoot ('.pre-harr-' + [guid]::NewGuid().ToString('N'))
        Snapshot-All $tmp
        New-Item -ItemType Directory -Force -Path $StateRoot | Out-Null
        Move-Item -LiteralPath $tmp -Destination $PreHarr
        Write-Host "Captured pre-Harr global harness snapshot: $PreHarr"
    }
    'safety-snapshot' {
        if (-not (Test-Path (Join-Path $PreHarr 'complete'))) { exit 0 }
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $root = Join-Path $BackupRoot $stamp
        Snapshot-All $root
        Write-Output $root
    }
    'restore' {
        if (-not (Test-Path (Join-Path $PreHarr 'complete'))) { throw "No pre-Harr snapshot found: $PreHarr" }
        foreach ($name in $Items.Keys) { Restore-Item $PreHarr $name }
        Restore-UserPath $PreHarr
        Restore-RegistryTasks $PreHarr
    }
    'status' {
        if (Test-Path (Join-Path $PreHarr 'complete')) { Write-Output "clean-snapshot`tready`t$PreHarr" }
        else { Write-Output "clean-snapshot`tmissing`t$PreHarr" }
    }
}
