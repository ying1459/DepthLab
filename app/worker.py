from __future__ import annotations

import ctypes
import os
import traceback
from pathlib import Path
from typing import Any

from app.depth_engine import DepthModel, ProcessingCancelled, VideoOptions, process_video


def configure_worker() -> None:
    """Keep inference responsive to the rest of Windows."""

    if os.name == "nt":
        below_normal_priority_class = 0x00004000
        kernel32 = ctypes.windll.kernel32
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), below_normal_priority_class)

    import torch

    threads = max(1, int(os.getenv("DEPTH_LAB_CPU_THREADS", "4")))
    torch.set_num_threads(threads)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass


def process_job_worker(
    source_path: str,
    output_path: str,
    options_data: dict[str, Any],
    progress_queue: Any,
    cancel_event: Any,
) -> None:
    """Run model loading and inference outside the desktop/UI process."""

    try:
        configure_worker()
        model = DepthModel()
        metadata = process_video(
            Path(source_path),
            Path(output_path),
            VideoOptions(**options_data),
            model,
            lambda progress, message, current, total: progress_queue.put(
                {
                    "kind": "progress",
                    "progress": progress,
                    "message": message,
                    "current": current,
                    "total": total,
                }
            ),
            cancel_event.is_set,
        )
        progress_queue.put({"kind": "completed", "metadata": metadata})
    except ProcessingCancelled:
        progress_queue.put({"kind": "cancelled"})
    except BaseException as exc:
        progress_queue.put(
            {
                "kind": "failed",
                "error": str(exc) or exc.__class__.__name__,
                "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            }
        )
