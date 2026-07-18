$ErrorActionPreference = "Stop"

Write-Host "build_exe.ps1 now uses the supported onedir release build."
& (Join-Path $PSScriptRoot "build_release.ps1")
