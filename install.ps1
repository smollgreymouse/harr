[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$Start,
    [switch]$HarrOnly,
    [switch]$NoPathUpdate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'PowerShell installation is currently for Windows; use ./install.sh on Unix platforms' }
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $root 'windows\install.ps1') @PSBoundParameters
