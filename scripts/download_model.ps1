$ErrorActionPreference = "Stop"

$modelUrl = "https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf/resolve/main/model.safetensors?download=true"
$expectedSha256 = "3152477CE0D8D6978D76B995120DE97CB5B928701FD0F817769F59E249A16B70"
$expectedBytes = 99173660
$modelDir = Join-Path (Split-Path $PSScriptRoot -Parent) "models\small"
$target = Join-Path $modelDir "model.safetensors"
$partial = "$target.part"

New-Item -ItemType Directory -Path $modelDir -Force | Out-Null

if (Test-Path -LiteralPath $target) {
    $existing = Get-Item -LiteralPath $target
    $existingHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    if ($existing.Length -eq $expectedBytes -and $existingHash -eq $expectedSha256) {
        Write-Host "Depth Anything V2 Small is already present and verified."
        exit 0
    }
}

Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
Write-Host "Downloading the official Depth Anything V2 Small checkpoint..."
Invoke-WebRequest -Uri $modelUrl -OutFile $partial -UseBasicParsing

$download = Get-Item -LiteralPath $partial
$downloadHash = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash
if ($download.Length -ne $expectedBytes -or $downloadHash -ne $expectedSha256) {
    Remove-Item -LiteralPath $partial -Force
    throw "Model verification failed. The downloaded file was removed."
}

Move-Item -LiteralPath $partial -Destination $target -Force
Write-Host "Model downloaded and verified: $target"
