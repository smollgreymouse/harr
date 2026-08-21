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
$UserHome = if ($env:HARR_HOME) { $env:HARR_HOME } elseif ($env:USERPROFILE) { $env:USERPROFILE } else { [Environment]::GetFolderPath('UserProfile') }
$ConfigHome = if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { Join-Path $UserHome '.config' }
$Manager = Join-Path $HarrRoot 'libexec\common\mcp\manager.py'
$Effective = Join-Path $ConfigHome 'harr\mcp-registry.json'
$NpmBin = Join-Path $HarrRoot 'share\npm\node_modules\.bin'
$env:HARR_NPM_BIN_DIR = $NpmBin
$name = $Arguments[0]

if (-not (Test-Path -LiteralPath $Effective)) { throw "Harr MCP selection is missing: $Effective. Run: harr mcp configure" }

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
    & $python.Source @prefix $Manager --registry $Effective run @Arguments *>> $logFile
} else {
    & $python.Source @prefix $Manager --registry $Effective run @Arguments
}
exit $LASTEXITCODE
