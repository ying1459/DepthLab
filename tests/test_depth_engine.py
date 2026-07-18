import subprocess

import cv2
import imageio_ffmpeg
import numpy as np

from app.depth_engine import finalize_video


def test_finalize_video_creates_browser_compatible_h264(tmp_path) -> None:
    silent = tmp_path / "silent.mp4"
    output = tmp_path / "result.mp4"
    writer = cv2.VideoWriter(
        str(silent),
        cv2.VideoWriter_fourcc(*"mp4v"),
        4.0,
        (64, 48),
    )
    assert writer.isOpened()
    for value in (0, 96, 192, 255):
        writer.write(np.full((48, 64, 3), value, dtype=np.uint8))
    writer.release()

    finalize_video(silent, silent, output, keep_audio=False)

    assert output.exists()
    assert not silent.exists()
    probe = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(output)],
        capture_output=True,
        text=True,
    )
    assert "Video: h264" in probe.stderr
