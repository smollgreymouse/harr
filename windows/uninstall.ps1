Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$UserHome = if ($env:HARR_HOME) { $env:HARR_HOME } elseif ($env:USERPROFILE) { $env:USERPROFILE } else { [Environment]::GetFolderPath('UserProfile') }
$LocalRoot = if ($env:HARR_LOCALAPPDATA) { $env:HARR_LOCALAPPDATA } elseif ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $UserHome 'AppData\Local' }
$harr = Join-Path $LocalRoot 'Harr\libexec\harr.ps1'
if (-not (Test-Path -LiteralPath $harr)) { throw "Installed Harr CLI not found: $harr" }
& $harr uninstall
