from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np


MODEL_IDS = {
    "small": "depth-anything/Depth-Anything-V2-Small-hf",
    "base": "depth-anything/Depth-Anything-V2-Base-hf",
    "large": "depth-anything/Depth-Anything-V2-Large-hf",
}

PALETTES = {
    "turbo": cv2.COLORMAP_TURBO,
    "inferno": cv2.COLORMAP_INFERNO,
    "viridis": cv2.COLORMAP_VIRIDIS,
    "magma": cv2.COLORMAP_MAGMA,
}


class ProcessingCancelled(Exception):
    pass


@dataclass(frozen=True)
class VideoOptions:
    model: str = "small"
    mode: str = "depth"
    palette: str = "turbo"
    max_side: int = 512
    output_fps: float = 12
    smoothing: float = 0.82
    invert: bool = False
    keep_audio: bool = True


class DepthModel:
    """Lazily owns one Transformers model so repeated jobs stay fast."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._model_key: str | None = None
        self._model = None
        self._processor = None
        self._device = None
        requested_size = int(os.getenv("DEPTH_LAB_INFERENCE_SIZE", "392"))
        self._inference_size = max(280, min(518, requested_size))
        self._inference_size -= self._inference_size % 14

    @property
    def device_label(self) -> str:
        try:
            import torch

            if torch.cuda.is_available():
                return f"CUDA · {torch.cuda.get_device_name(0)}"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "Apple MPS"
        except ImportError:
            pass
        return "CPU"

    def load(self, model_key: str, progress: Callable[[str], None]) -> None:
        if model_key not in MODEL_IDS:
            raise ValueError(f"Unknown model: {model_key}")
        with self._lock:
            if self._model_key == model_key:
                return

            progress("正在启动内置 Depth 引擎")
            import torch
            from transformers import AutoImageProcessor, AutoModelForDepthEstimation

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            if device.type == "cpu" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = torch.device("mps")

            model_source: str | Path = MODEL_IDS[model_key]
            bundled_root = os.getenv("DEPTH_LAB_MODEL_DIR")
            if bundled_root:
                bundled_model = Path(bundled_root) / model_key
                if (bundled_model / "model.safetensors").is_file():
                    model_source = bundled_model

            if os.getenv("DEPTH_LAB_OFFLINE") == "1" and isinstance(model_source, str):
                raise RuntimeError("该版本只允许使用程序内置的离线模型")

            processor = AutoImageProcessor.from_pretrained(model_source)
            model = AutoModelForDepthEstimation.from_pretrained(model_source)
            model.to(device)
            model.eval()

            self._processor = processor
            self._model = model
            self._device = device
            self._model_key = model_key

    def infer(self, frame_bgr: np.ndarray) -> np.ndarray:
        import torch
        import torch.nn.functional as functional
        from PIL import Image

        if self._model is None or self._processor is None or self._device is None:
            raise RuntimeError("Depth model has not been loaded")

        image = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        inputs = self._processor(
            images=image,
            return_tensors="pt",
            size={"height": self._inference_size, "width": self._inference_size},
        )
        inputs = {key: value.to(self._device) for key, value in inputs.items()}

        with self._lock, torch.inference_mode():
            use_amp = self._device.type == "cuda"
            with torch.autocast(device_type=self._device.type, dtype=torch.float16, enabled=use_amp):
                prediction = self._model(**inputs).predicted_depth
            prediction = functional.interpolate(
                prediction.unsqueeze(1),
                size=frame_bgr.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()

        return prediction.float().cpu().numpy()


def resize_for_output(frame: np.ndarray, max_side: int) -> np.ndarray:
    height, width = frame.shape[:2]
    if max_side <= 0 or max(height, width) <= max_side:
        result = frame
    else:
        scale = max_side / max(height, width)
        result = cv2.resize(frame, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)

    height, width = result.shape[:2]
    even_width = width - (width % 2)
    even_height = height - (height % 2)
    return result[:even_height, :even_width]


def colorize_depth(depth_u8: np.ndarray, palette: str) -> np.ndarray:
    if palette == "gray":
        return cv2.cvtColor(depth_u8, cv2.COLOR_GRAY2BGR)
    color_map = PALETTES.get(palette, cv2.COLORMAP_TURBO)
    return cv2.applyColorMap(depth_u8, color_map)


def compose_frame(original: np.ndarray, depth_color: np.ndarray, mode: str) -> np.ndarray:
    if mode == "blend":
        return cv2.addWeighted(original, 0.38, depth_color, 0.62, 0)
    if mode == "side-by-side":
        return np.concatenate([original, depth_color], axis=1)
    return depth_color


def finalize_video(
    silent_video: Path,
    source_video: Path,
    output_video: Path,
    keep_audio: bool,
) -> None:
    """Create a browser-compatible H.264 MP4 and optionally preserve source audio."""

    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("程序缺少视频编码组件，请重新安装 Depth Lab") from exc

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(silent_video),
    ]
    if keep_audio:
        command.extend(["-i", str(source_video), "-map", "0:v:0", "-map", "1:a:0?"])
    else:
        command.extend(["-map", "0:v:0", "-an"])

    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-threads",
            "2",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
        ]
    )
    if keep_audio:
        command.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
    command.append(str(output_video))

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        output_video.unlink(missing_ok=True)
        raise RuntimeError("无法生成可预览的 MP4，请检查磁盘空间后重试") from exc
    else:
        silent_video.unlink(missing_ok=True)


def process_video(
    source: Path,
    destination: Path,
    options: VideoOptions,
    model: DepthModel,
    on_progress: Callable[[float, str, int, int], None],
    is_cancelled: Callable[[], bool],
) -> dict[str, float | int | str]:
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError("无法读取该视频，请尝试 MP4、MOV、AVI 或 WebM 格式")

    source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    source_fps = source_fps if 0.1 <= source_fps <= 240 else 30.0
    source_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    output_fps = source_fps if options.output_fps <= 0 else min(options.output_fps, source_fps)
    ratio = source_fps / output_fps
    estimated_output_frames = max(1, round(source_frames / ratio)) if source_frames else 0

    model.load(options.model, lambda message: on_progress(0.02, message, 0, estimated_output_frames))
    if is_cancelled():
        capture.release()
        raise ProcessingCancelled()

    ok, first_frame = capture.read()
    if not ok:
        capture.release()
        raise ValueError("视频中没有可读取的画面")
    first_frame = resize_for_output(first_frame, options.max_side)
    frame_height, frame_width = first_frame.shape[:2]
    output_width = frame_width * 2 if options.mode == "side-by-side" else frame_width

    silent_path = destination.with_name("depth_silent.mp4")
    writer = cv2.VideoWriter(
        str(silent_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        output_fps,
        (output_width, frame_height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("无法创建输出视频，请检查磁盘空间")

    frame_index = 0
    output_index = 0
    next_source_frame = 0.0
    bounds: tuple[float, float] | None = None
    current_frame: np.ndarray | None = first_frame

    try:
        while current_frame is not None:
            if is_cancelled():
                raise ProcessingCancelled()

            if frame_index + 1e-6 >= next_source_frame:
                frame = resize_for_output(current_frame, options.max_side)
                depth = model.infer(frame)
                low, high = np.percentile(depth, (2.0, 98.0))
                if high - low < 1e-6:
                    high = low + 1e-6

                if bounds is None:
                    bounds = (float(low), float(high))
                else:
                    smooth = min(0.98, max(0.0, options.smoothing))
                    bounds = (
                        bounds[0] * smooth + float(low) * (1 - smooth),
                        bounds[1] * smooth + float(high) * (1 - smooth),
                    )

                normalized = np.clip((depth - bounds[0]) / (bounds[1] - bounds[0]), 0, 1)
                if options.invert:
                    normalized = 1 - normalized
                depth_u8 = (normalized * 255).astype(np.uint8)
                depth_color = colorize_depth(depth_u8, options.palette)
                writer.write(compose_frame(frame, depth_color, options.mode))

                output_index += 1
                next_source_frame += ratio
                denominator = estimated_output_frames or max(output_index, 1)
                fraction = min(0.96, 0.04 + 0.91 * output_index / denominator)
                on_progress(fraction, "正在分析空间深度", output_index, estimated_output_frames)

            frame_index += 1
            ok, read_frame = capture.read()
            current_frame = read_frame if ok else None
    finally:
        writer.release()
        capture.release()

    if is_cancelled():
        silent_path.unlink(missing_ok=True)
        raise ProcessingCancelled()
    if output_index == 0:
        silent_path.unlink(missing_ok=True)
        raise ValueError("未能从视频中提取画面")

    on_progress(0.97, "正在生成兼容视频", output_index, output_index)
    finalize_video(silent_path, source, destination, options.keep_audio)
    on_progress(1.0, "处理完成", output_index, output_index)

    return {
        "frames": output_index,
        "fps": round(output_fps, 3),
        "width": output_width,
        "height": frame_height,
        "duration": round(output_index / output_fps, 3),
        "device": model.device_label,
    }
