param(
    [switch]$SkipAppBuild,
    [switch]$SkipPortableBuild
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$iss = Join-Path $root "installer\DepthLab.iss"
$versionMatch = Select-String -LiteralPath $iss -Pattern '^#define MyAppVersion "([^"]+)"$'
if (-not $versionMatch) {
    throw "Could not read MyAppVersion from installer\DepthLab.iss."
}
$version = $versionMatch.Matches[0].Groups[1].Value

Push-Location $root
try {
    if (-not $SkipAppBuild) {
        & (Join-Path $root "build_release.ps1")
        if ($LASTEXITCODE -ne 0) {
            throw "Application build failed with exit code $LASTEXITCODE."
        }
    }

    $releaseDir = Join-Path $root "release"
    New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
    $zip = Join-Path $releaseDir "DepthLab-Portable-$version-Windows-x64.zip"
    if (-not $SkipPortableBuild) {
        Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
        Compress-Archive -Path (Join-Path $root "dist\DepthLab\*") -DestinationPath $zip -CompressionLevel Optimal
    }
    elseif (-not (Test-Path -LiteralPath $zip)) {
        throw "Portable archive was not found: $zip"
    }

    $isccCandidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        (Join-Path $root ".build-tools\Inno Setup 6\ISCC.exe")
    )
    $iscc = $isccCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $iscc) {
        throw "Inno Setup 6 was not found. Install it and run this script again."
    }

    & $iscc $iss
    if ($LASTEXITCODE -ne 0) {
        throw "Installer build failed with exit code $LASTEXITCODE."
    }

    $setup = Join-Path $releaseDir "DepthLab-Setup-$version-Windows-x64.exe"
    if (-not (Test-Path -LiteralPath $setup)) {
        throw "Installer output was not found: $setup"
    }

    $checksumPath = Join-Path $releaseDir "SHA256SUMS.txt"
    $checksumLines = foreach ($file in @($setup, $zip)) {
        $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $([IO.Path]::GetFileName($file))"
    }
    Set-Content -LiteralPath $checksumPath -Value $checksumLines -Encoding ascii

    Write-Host "Release created:"
    Get-Item -LiteralPath $setup, $zip, $checksumPath | Select-Object Name, Length
}
finally {
    Pop-Location
}
