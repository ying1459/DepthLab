# Depth Lab

> Turn ordinary videos into smooth, previewable relative-depth videos.

[![Release](https://img.shields.io/github/v/release/ying1459/DepthLab?display_name=tag&sort=semver)](https://github.com/ying1459/DepthLab/releases/latest)
[![CI](https://github.com/ying1459/DepthLab/actions/workflows/ci.yml/badge.svg)](https://github.com/ying1459/DepthLab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D4?logo=windows)](https://github.com/ying1459/DepthLab/releases/latest)

[简体中文](README.md) · [Latest release](https://github.com/ying1459/DepthLab/releases/latest) · [Report an issue](https://github.com/ying1459/DepthLab/issues)

![Depth Lab user interface](docs/depth-lab-ui.png)

Depth Lab is a local monocular video-depth extraction tool powered by Depth Anything V2 Small. It estimates relative depth frame by frame and exports a standard H.264 MP4. The Windows builds bundle the AI model, FFmpeg, and runtime, so end users do not need Python or a separate model download.

## Highlights

- Local-first: source videos and results stay on your computer
- Ready to use: the Windows installer bundles the model and runtime
- Responsive UI: inference runs in a separate process with progress and cancellation
- Three output modes: depth, overlay, and side-by-side
- Five palettes: Turbo, grayscale, Inferno, Viridis, and Magma
- Temporal smoothing to reduce frame-to-frame depth flicker
- H.264 / yuv420p MP4 output for broad preview compatibility
- Optional source-audio preservation

## Download

Open the [latest GitHub Release](https://github.com/ying1459/DepthLab/releases/latest):

- `DepthLab-Setup-*-Windows-x64.exe`: installer, recommended for most users
- `DepthLab-Portable-*-Windows-x64.zip`: portable build; extract and run `DepthLab.exe`

System requirements: Windows 10/11 x64. No model download is required on first launch.

For the best CPU responsiveness, start with the default 512-pixel output and 12 FPS setting.

## Run from source

Python 3.10+ and access to Hugging Face are required. The repository intentionally excludes the 95 MB checkpoint; Transformers downloads the Small checkpoint when the first job runs.

```powershell
git clone https://github.com/ying1459/DepthLab.git
cd DepthLab
.\run.cmd
```

Then open <http://127.0.0.1:8000>.

## Build the Windows package

```powershell
.\scripts\download_model.ps1
py -m venv .build-venv
.\.build-venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\scripts\build_windows_release.ps1
```

The script creates the portable ZIP, installer, and `SHA256SUMS.txt`. Install [Inno Setup 6](https://jrsoftware.org/isinfo.php) before running it.

## Test

```powershell
python -m pip install -r requirements-ci.txt
pytest -q
```

## Limitations

Depth Lab produces monocular **relative depth**, not metric distance in meters. Relative scale can also change at shot boundaries.

## License

Depth Lab source code is released under the [MIT License](LICENSE). The bundled Depth Anything V2 Small checkpoint is licensed under Apache-2.0. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for details.
