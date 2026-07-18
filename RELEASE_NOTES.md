# Depth Lab 1.0.2

首个公开发布版本。Windows 安装包和免安装版都已内置 Depth Anything V2 Small 模型与 FFmpeg，普通用户无需安装 Python 或下载权重。

## 功能

- 将 MP4、MOV、AVI、WebM、MKV 转换为相对深度视频
- 支持纯深度、原片叠加、左右对比三种模式
- 支持 Turbo、灰度、Inferno、Viridis、Magma 色板
- 支持跨帧平滑、反转深度与保留原音轨
- 输出标准 H.264 / yuv420p MP4，可直接预览和保存
- AI 推理使用独立进程，界面保持响应并可立即取消

## 下载选择

- `DepthLab-Setup-1.0.2-Windows-x64.exe`：安装版，推荐
- `DepthLab-Portable-1.0.2-Windows-x64.zip`：免安装版

## 注意

输出是单目相对深度，不是以米为单位的精确测距数据。CPU 用户建议先使用默认的 512 输出尺寸和 12 FPS。

安装包目前没有商业代码签名证书。Windows SmartScreen 在首次下载时可能显示“未知发布者”，请仅从本仓库的 Releases 页面下载，并可使用随附的 `SHA256SUMS.txt` 校验文件完整性。
