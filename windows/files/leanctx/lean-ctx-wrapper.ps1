Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$HarrRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..'))
$UserHome = if ($env:HARR_HOME) { $env:HARR_HOME } elseif ($env:USERPROFILE) { $env:USERPROFILE } else { [Environment]::GetFolderPath('UserProfile') }
$ConfigHome = if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { Join-Path $UserHome '.config' }
$Real = Join-Path $HarrRoot 'libexec\vendor\lean-ctx\3.9.15\lean-ctx.exe'
$Manager = Join-Path $HarrRoot 'libexec\common\mcp\manager.py'
$NpmBin = Join-Path $HarrRoot 'share\npm\node_modules\.bin'
$BinDir = Join-Path $HarrRoot 'bin'
$LeanConfigDir = Join-Path $ConfigHome 'lean-ctx'

if (-not (Test-Path -LiteralPath $Real)) { throw "Harr LeanCTX binary is missing: $Real" }
if (-not (Test-Path -LiteralPath $Manager)) { throw "Harr MCP manager is missing: $Manager" }
$env:LEAN_CTX_CONFIG_DIR = $LeanConfigDir
$env:HARR_NPM_BIN_DIR = $NpmBin
$env:Path = "$BinDir;$NpmBin;$env:Path"

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($python) {
    & $python.Source $Manager exec-leanctx $Real -- @args
    exit $LASTEXITCODE
}
$py = Get-Command py.exe -ErrorAction SilentlyContinue
if ($py) {
    & $py.Source -3 $Manager exec-leanctx $Real -- @args
    exit $LASTEXITCODE
}
throw 'Python 3 is required by Harr LeanCTX launcher'
