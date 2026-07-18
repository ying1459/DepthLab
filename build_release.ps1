$ErrorActionPreference = "Stop"

$python = ".\.build-venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Build environment not found. Create .build-venv before running this script."
}
$root = (Resolve-Path ".").Path
$modelWeight = Join-Path $root "models\small\model.safetensors"
$expectedModelSha256 = "3152477CE0D8D6978D76B995120DE97CB5B928701FD0F817769F59E249A16B70"

if (-not (Test-Path -LiteralPath $modelWeight)) {
    throw "Bundled model not found. Run .\scripts\download_model.ps1 first."
}

$modelHash = (Get-FileHash -LiteralPath $modelWeight -Algorithm SHA256).Hash
if ($modelHash -ne $expectedModelSha256) {
    throw "Bundled model SHA-256 verification failed. Run .\scripts\download_model.ps1 again."
}

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --splash "$root\app\static\splash.png" `
    --icon "$root\app\static\depthlab.ico" `
    --version-file "$root\version_info.txt" `
    --name DepthLab `
    --contents-directory _internal `
    --distpath "dist" `
    --workpath "build\pyinstaller-release" `
    --specpath "build" `
    --add-data "$root\app\static;app\static" `
    --add-data "$root\models;models" `
    --collect-all imageio_ffmpeg `
    --collect-all webview `
    --collect-submodules uvicorn `
    --collect-submodules transformers.models.depth_anything `
    --collect-submodules transformers.models.dinov2 `
    --collect-submodules transformers.models.dpt `
    --hidden-import cv2 `
    --hidden-import PIL `
    --hidden-import numpy `
    --hidden-import torch `
    --hidden-import multipart `
    --hidden-import clr `
    --hidden-import webview.platforms.edgechromium `
    "$root\app\launcher.py"

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE."
}

$distRoot = Join-Path $root "dist\DepthLab"
Copy-Item -LiteralPath (Join-Path $root "LICENSE") -Destination $distRoot -Force
Copy-Item -LiteralPath (Join-Path $root "THIRD_PARTY_NOTICES.md") -Destination $distRoot -Force
New-Item -ItemType Directory -Path (Join-Path $distRoot "LICENSES") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $root "LICENSES\Apache-2.0.txt") -Destination (Join-Path $distRoot "LICENSES") -Force
