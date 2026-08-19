Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:HarrVersion = '0.6.0'
$script:LeanVersion = '3.9.15'
$script:UserHome = if ($env:HARR_HOME) { $env:HARR_HOME } elseif ($env:USERPROFILE) { $env:USERPROFILE } else { [Environment]::GetFolderPath('UserProfile') }
$script:LocalRoot = if ($env:HARR_LOCALAPPDATA) { $env:HARR_LOCALAPPDATA } elseif ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $UserHome 'AppData\Local' }
$script:ConfigHome = if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { Join-Path $UserHome '.config' }
$script:CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $UserHome '.codex' }
$script:OpenCodeHome = Join-Path $ConfigHome 'opencode'
$script:HarrRoot = Join-Path $LocalRoot 'Harr'
$script:BinDir = Join-Path $HarrRoot 'bin'
$script:LibExecDir = Join-Path $HarrRoot 'libexec'
$script:CommonDir = Join-Path $LibExecDir 'common'
$script:WindowsDir = Join-Path $LibExecDir 'windows'
$script:Manager = Join-Path $CommonDir 'mcp\manager.py'
$script:Selector = Join-Path $CommonDir 'mcp\selector.py'
$script:Assets = Join-Path $CommonDir 'mcp\assets.py'
$script:McpCatalog = Join-Path $CommonDir 'mcp\registry.json'
$script:NpmPrefix = Join-Path $HarrRoot 'share\npm'
$script:NpmBin = Join-Path $NpmPrefix 'node_modules\.bin'
$script:VendorDir = Join-Path $LibExecDir 'vendor'
$script:HarrConfig = Join-Path $ConfigHome 'harr'
$script:McpConfig = Join-Path $HarrConfig 'mcp'
$script:McpSelection = Join-Path $HarrConfig 'mcp-selection.json'
$script:McpEffective = Join-Path $HarrConfig 'mcp-registry.json'
$script:SecretsDir = Join-Path $HarrConfig 'secrets'
$script:LeanConfigDir = Join-Path $ConfigHome 'lean-ctx'
$script:LeanConfig = Join-Path $LeanConfigDir 'config.toml'
$script:StateRoot = Join-Path $LocalRoot 'HarrState'
$script:StateHelper = Join-Path $StateRoot 'harr-state.ps1'
$script:CleanMarker = Join-Path $StateRoot 'pre-harr\complete'
$script:LeanCommand = Join-Path $BinDir 'lean-ctx.cmd'
$script:McpRunner = Join-Path $BinDir 'harr-mcp-run.cmd'
$script:LogDir = Join-Path $HarrRoot 'logs'

function Write-Utf8([string]$Path, [string]$Value) {
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    [IO.File]::WriteAllText($Path, $Value, (New-Object Text.UTF8Encoding($false)))
}

function Require-CleanOwnership {
    if (-not (Test-Path -LiteralPath $CleanMarker)) { throw 'Harr has not taken clean ownership; run install.ps1 -Clean first' }
}

function Resolve-Python {
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) { return [string[]]@($python.Source) }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return [string[]]@($python.Source) }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) { return [string[]]@($py.Source, '-3') }
    throw 'Python 3 is required for Harr'
}

function Invoke-Python([string[]]$CommandArgs, [switch]$AllowFailure) {
    [string[]]$cmd = @(Resolve-Python)
    $exe = $cmd[0]
    [string[]]$prefix = @()
    if ($cmd.Count -gt 1) { $prefix = @($cmd[1..($cmd.Count - 1)]) }
    & $exe @prefix @CommandArgs
    $code = $LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFailure) { throw "Python command failed ($code)" }
    return $code
}

function Python-Lines([string[]]$CommandArgs) {
    [string[]]$cmd = @(Resolve-Python)
    $exe = $cmd[0]
    [string[]]$prefix = @()
    if ($cmd.Count -gt 1) { $prefix = @($cmd[1..($cmd.Count - 1)]) }
    [string[]]$lines = @(& $exe @prefix @CommandArgs)
    if ($LASTEXITCODE -ne 0) { throw "Python command failed: $($CommandArgs -join ' ')" }
    return $lines
}

function Ensure-McpEffective {
    if ((Test-Path -LiteralPath $McpSelection) -and (Test-Path -LiteralPath $McpEffective)) { return }
    New-Item -ItemType Directory -Force -Path $HarrConfig | Out-Null
    [void](Invoke-Python @($Selector, '--catalog', $McpCatalog, '--selection', $McpSelection, '--effective', $McpEffective, '--default', 'all'))
}

function Manager-Lines([string[]]$CommandArgs) {
    Ensure-McpEffective
    [string[]]$managerArgs = @($Manager, '--registry', $McpEffective) + $CommandArgs
    return [string[]]@(Python-Lines $managerArgs)
}

function Invoke-Manager([string[]]$CommandArgs) {
    Ensure-McpEffective
    [string[]]$managerArgs = @($Manager, '--registry', $McpEffective) + $CommandArgs
    [void](Invoke-Python $managerArgs)
}

function Catalog-Manager-Lines([string[]]$CommandArgs) {
    [string[]]$managerArgs = @($Manager, '--registry', $McpCatalog) + $CommandArgs
    return [string[]]@(Python-Lines $managerArgs)
}

function Active-McpNames { return [string[]]@(Manager-Lines @('names')) }
function Catalog-McpServers {
    if (-not (Test-Path -LiteralPath $McpCatalog)) { return [object[]]@() }
    return [object[]]@((Get-Content -Raw -LiteralPath $McpCatalog | ConvertFrom-Json).servers)
}

function Read-Adapter([string]$Name) {
    $path = Join-Path $CommonDir ("hosts\$Name.env")
    $map = @{}
    foreach ($line in Get-Content -LiteralPath $path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        $pair = $trimmed.Split('=', 2)
        if ($pair.Count -ne 2) { continue }
        $value = $pair[1].Trim()
        if (($value.StartsWith("'") -and $value.EndsWith("'")) -or ($value.StartsWith('"') -and $value.EndsWith('"'))) { $value = $value.Substring(1, $value.Length - 2) }
        $map[$pair[0]] = $value
    }
    return $map
}

function Render-Policy([string]$Agent) {
    $text = Get-Content -Raw -LiteralPath (Join-Path $CommonDir 'policy\tool-routing.template.md')
    $adapter = Read-Adapter $Agent
    foreach ($name in @('CTX_READ','CTX_SHELL','CTX_SEARCH','CTX_GLOB','CTX_TOOLS','CTX_CALL','HOST_NATIVE_POLICY')) {
        if (-not $adapter.ContainsKey($name)) { throw "Incomplete Harr host adapter: $Agent ($name missing)" }
        $text = $text.Replace("{{$name}}", [string]$adapter[$name])
    }
    Ensure-McpEffective
    $input = [IO.Path]::GetTempFileName()
    $output = [IO.Path]::GetTempFileName()
    try {
        Write-Utf8 $input $text
        [void](Invoke-Python @($Assets, 'filter-text', '--catalog', $McpCatalog, '--registry', $McpEffective, '--input', $input, '--output', $output))
        return Get-Content -Raw -LiteralPath $output
    } finally { Remove-Item $input,$output -Force -ErrorAction SilentlyContinue }
}

function Agent-PolicyPath([string]$Agent) {
    if ($Agent -eq 'codex') { return Join-Path $CodexHome 'AGENTS.md' }
    if ($Agent -eq 'opencode') { return Join-Path $OpenCodeHome 'AGENTS.md' }
    throw "Unknown agent: $Agent"
}
function Agent-SkillRoot([string]$Agent) {
    if ($Agent -eq 'codex') { return Join-Path $CodexHome 'skills' }
    if ($Agent -eq 'opencode') { return Join-Path $OpenCodeHome 'skills' }
    throw "Unknown agent: $Agent"
}
function Copy-TreeFresh([string]$Source, [string]$Target) {
    if (Test-Path -LiteralPath $Target) { Remove-Item -LiteralPath $Target -Recurse -Force }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Target -Recurse -Force
}
function Install-HarrSkill([string]$Target) {
    Ensure-McpEffective
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
    [void](Invoke-Python @($Assets, 'filter-skill', '--catalog', $McpCatalog, '--registry', $McpEffective, '--source', (Join-Path $CommonDir 'skills\harr'), '--output', $Target))
}

function Apply-Agents([string]$Requested = 'all') {
    Require-CleanOwnership
    [string[]]$agents = if ($Requested -eq 'all') { @('codex','opencode') } elseif ($Requested -in @('codex','opencode')) { @($Requested) } else { throw 'usage: harr agents apply [all|codex|opencode]' }
    foreach ($agent in $agents) {
        $policy = Agent-PolicyPath $agent
        Write-Utf8 $policy (Render-Policy $agent)
        Copy-TreeFresh (Join-Path $CommonDir 'skills\lean-ctx') (Join-Path (Agent-SkillRoot $agent) 'lean-ctx')
        Install-HarrSkill (Join-Path (Agent-SkillRoot $agent) 'harr')
        Write-Host "Applied Harr-owned global policy for ${agent}: $policy"
    }
}

function Policy-State([string]$Agent) {
    $target = Agent-PolicyPath $Agent
    if (-not (Test-Path $target)) { return 'missing' }
    $expected = Render-Policy $Agent
    $actual = Get-Content -Raw -LiteralPath $target
    if ($actual -eq $expected) { return 'managed' }
    if ($actual.Contains('<!-- harr-tool-policy:start -->')) { return 'modified' }
    return 'external'
}

function Apply-Hosts {
    $env:HARR_LEANCTX_COMMAND = $LeanCommand
    [void](Invoke-Python -CommandArgs @((Join-Path $CommonDir 'hosts\opencode-config.py'), 'apply'))
    [void](Invoke-Python -CommandArgs @((Join-Path $CommonDir 'hosts\codex-config.py'), 'apply'))
}
function Hosts-Status {
    $env:HARR_LEANCTX_COMMAND = $LeanCommand
    [void](Invoke-Python -CommandArgs @((Join-Path $CommonDir 'hosts\opencode-config.py'), 'status') -AllowFailure)
    [void](Invoke-Python -CommandArgs @((Join-Path $CommonDir 'hosts\codex-config.py'), 'status') -AllowFailure)
}
