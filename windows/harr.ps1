[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ModuleDir = Join-Path $PSScriptRoot 'windows\files\harr-cli'
. (Join-Path $ModuleDir 'common.ps1')
. (Join-Path $ModuleDir 'mcp.ps1')
. (Join-Path $ModuleDir 'runtime.ps1')

function Show-Help {
    @'
Harr Windows CLI

  harr status
  harr install [all|leanctx|mcp]
  harr agents apply [all|codex|opencode]
  harr agents status
  harr hosts apply|status
  harr leanctx apply|status
  harr secret set NAME
  harr secret status
  harr secret unset NAME
  harr mcp list
  harr mcp available
  harr mcp configure [none|all|name1,name2]
  harr mcp start|stop|restart NAME|all
  harr mcp status
  harr mcp logs NAME
  harr uninstall
'@ | Write-Host
}

[string[]]$argv = @($Arguments)
$command = if ($argv.Count -gt 0) { $argv[0] } else { 'help' }
[string[]]$rest = @()
if ($argv.Count -gt 1) { $rest = @($argv[1..($argv.Count - 1)]) }

switch ($command) {
    'install' { Install-Components ($(if ($rest.Count) { $rest[0] } else { 'all' })) }
    'registry' {
        if ($rest.Count -and $rest[0] -eq 'apply') { Registry-Apply }
        else { throw 'usage: harr registry apply' }
    }
    'agents' {
        $sub = if ($rest.Count) { $rest[0] } else { 'status' }
        if ($sub -eq 'apply') { Apply-Agents ($(if ($rest.Count -gt 1) { $rest[1] } else { 'all' })) }
        elseif ($sub -eq 'status') { foreach ($agent in @('codex','opencode')) { Write-Host "$agent policy: $(Policy-State $agent)" } }
        else { throw 'usage: harr agents apply [all|codex|opencode] | harr agents status' }
    }
    'hosts' {
        $sub = if ($rest.Count) { $rest[0] } else { 'status' }
        if ($sub -eq 'apply') { Apply-Hosts }
        elseif ($sub -eq 'status') { Hosts-Status }
        else { throw 'usage: harr hosts apply|status' }
    }
    'leanctx' {
        $sub = if ($rest.Count) { $rest[0] } else { 'status' }
        if ($sub -eq 'apply') { Apply-LeanCtx }
        elseif ($sub -eq 'status') {
            Write-Host ($(if (Test-Path $LeanConfig) { "leanctx-config present $LeanConfig" } else { "leanctx-config missing $LeanConfig" }))
            Secret-Command status
        } else { throw 'usage: harr leanctx apply|status' }
    }
    'secret' {
        $sub = if ($rest.Count) { $rest[0] } else { 'status' }
        $name = if ($rest.Count -gt 1) { $rest[1] } else { '' }
        Secret-Command $sub $name
    }
    'mcp' {
        $sub = if ($rest.Count) { $rest[0] } else { 'status' }
        if ($sub -eq 'list') { foreach ($name in @(All-Mcp-Names)) { Write-Host $name } }
        elseif ($sub -eq 'available') { Mcp-Available }
        elseif ($sub -eq 'configure') { Mcp-Configure ($(if ($rest.Count -gt 1) { $rest[1] } else { '' })) }
        elseif ($sub -in @('start','stop','restart')) {
            $target = if ($rest.Count -gt 1) { $rest[1] } else { throw 'MCP target required' }
            Mcp-Action $sub $target
        }
        elseif ($sub -eq 'status') { Mcp-Status }
        elseif ($sub -eq 'logs') {
            $name = if ($rest.Count -gt 1) { $rest[1] } else { throw 'MCP name required' }
            Mcp-Logs $name
        }
        else { throw 'usage: harr mcp list|available|configure|start|stop|restart|status|logs' }
    }
    'status' {
        Write-Host '== MCP selection =='; Mcp-Available; Write-Host ''
        Components-Status
        Hosts-Status
        foreach ($agent in @('codex','opencode')) { Write-Host "$agent policy: $(Policy-State $agent)" }
        Secret-Command status
        Mcp-Status
    }
    'uninstall' { Uninstall-Harr }
    'version' { Write-Host "Harr $HarrVersion" }
    '--version' { Write-Host "Harr $HarrVersion" }
    '-V' { Write-Host "Harr $HarrVersion" }
    'help' { Show-Help }
    '--help' { Show-Help }
    '-h' { Show-Help }
    default { throw "Unknown Harr command: $command" }
}
