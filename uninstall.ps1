Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'PowerShell uninstall is currently for Windows; use ./uninstall.sh on Unix platforms' }
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $root 'windows\uninstall.ps1')
