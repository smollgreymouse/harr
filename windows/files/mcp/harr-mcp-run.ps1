[CmdletBinding()]
param(
    [switch]$Log,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($Arguments.Count -lt 1) { throw 'usage: harr-mcp-run [-Log] <name>' }

$HarrRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..'))
$Manager = Join-Path $HarrRoot 'libexec\common\mcp\manager.py'
$NpmBin = Join-Path $HarrRoot 'share\npm\node_modules\.bin'
$env:HARR_NPM_BIN_DIR = $NpmBin
$name = $Arguments[0]

$python = Get-Command python.exe -ErrorAction SilentlyContinue
$prefix = @()
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if (-not $python) {
    $python = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($python) { $prefix = @('-3') }
}
if (-not $python) { throw 'Python 3 is required by the Harr MCP runner' }

if ($Log) {
    $logDir = Join-Path $HarrRoot 'logs'
    $logFile = Join-Path $logDir "$name.log"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    "[$(Get-Date -Format o)] starting MCP $name" | Out-File -FilePath $logFile -Append -Encoding utf8
    & $python.Source @prefix $Manager run @Arguments *>> $logFile
} else {
    & $python.Source @prefix $Manager run @Arguments
}
exit $LASTEXITCODE
