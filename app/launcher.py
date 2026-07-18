from __future__ import annotations

import multiprocessing
import os
import shutil
import socket
import sys
import threading
import time
import traceback
from pathlib import Path


APP_NAME = "Depth Lab"


class DesktopApi:
    """Native desktop actions exposed to the local web interface."""

    def __init__(self) -> None:
        self.window = None

    def attach_window(self, window) -> None:
        self.window = window

    def save_result(self, job_id: str) -> dict:
        try:
            import webview
            from app.main import jobs, jobs_lock

            with jobs_lock:
                job = jobs.get(job_id)
            if job is None or job.state != "completed" or not job.output_path.exists():
                return {"ok": False, "error": "结果文件不存在，请重新处理视频"}
            if self.window is None:
                return {"ok": False, "error": "保存窗口尚未准备好"}

            invalid = '<>:"/\\|?*'
            stem = "".join("_" if char in invalid else char for char in Path(job.filename).stem)
            stem = stem.strip().strip(".") or "depth_result"
            downloads = Path.home() / "Downloads"
            initial_dir = downloads if downloads.is_dir() else Path.home()
            selected = self.window.create_file_dialog(
                webview.FileDialog.SAVE,
                directory=str(initial_dir),
                save_filename=f"{stem}_depth.mp4",
                file_types=("MP4 视频 (*.mp4)",),
            )
            if not selected:
                return {"ok": False, "cancelled": True}

            target = Path(selected[0])
            if target.suffix.lower() != ".mp4":
                target = target.with_suffix(".mp4")
            if target.resolve() != job.output_path.resolve():
                shutil.copy2(job.output_path, target)
            return {"ok": True, "path": str(target)}
        except Exception as exc:
            return {"ok": False, "error": f"保存失败：{exc}"}


def resource_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parent.parent


def configure_paths() -> Path:
    root = resource_root()
    local_app_data = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    writable_data = local_app_data / "DepthLab" / "jobs"
    writable_data.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DEPTH_LAB_DATA", str(writable_data))
    os.environ.setdefault("DEPTH_LAB_MODEL_DIR", str(root / "models"))
    os.environ.setdefault("DEPTH_LAB_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    cpu_threads = str(max(2, min(4, (os.cpu_count() or 4) // 2)))
    os.environ.setdefault("DEPTH_LAB_CPU_THREADS", cpu_threads)
    os.environ.setdefault("DEPTH_LAB_INFERENCE_SIZE", "392")
    os.environ.setdefault("OMP_NUM_THREADS", cpu_threads)
    os.environ.setdefault("MKL_NUM_THREADS", cpu_threads)
    os.environ.setdefault("OPENBLAS_NUM_THREADS", cpu_threads)
    os.environ.setdefault("NUMEXPR_NUM_THREADS", cpu_threads)
    os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
    os.environ.setdefault("KMP_BLOCKTIME", "0")
    return writable_data


def write_crash_log(error: BaseException) -> Path:
    local_app_data = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    log_dir = local_app_data / "DepthLab"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "launcher-error.log"
    log_path.write_text(
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        encoding="utf-8",
    )
    return log_path


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until_ready(port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def close_splash() -> None:
    try:
        import pyi_splash

        pyi_splash.close()
    except ImportError:
        pass


def run() -> int:
    data_dir = configure_paths()
    port = free_port()
    url = f"http://127.0.0.1:{port}"

    import uvicorn
    from app.main import app

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        log_config=None,
    )
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, name="depth-lab-server", daemon=True)
    server_thread.start()

    if not wait_until_ready(port):
        raise RuntimeError("The local Depth Lab service did not start")

    close_splash()

    try:
        if os.getenv("DEPTH_LAB_HEADLESS") == "1":
            while server_thread.is_alive() and not server.should_exit:
                time.sleep(0.25)
        else:
            import webview

            desktop_api = DesktopApi()
            window = webview.create_window(
                APP_NAME,
                url,
                width=1360,
                height=900,
                min_size=(980, 680),
                background_color="#080c0b",
                confirm_close=False,
                text_select=False,
                js_api=desktop_api,
            )
            desktop_api.attach_window(window)
            auto_close_seconds = float(os.getenv("DEPTH_LAB_AUTOCLOSE_SECONDS", "0"))
            if auto_close_seconds > 0:
                window.events.shown += lambda: threading.Timer(
                    auto_close_seconds,
                    window.destroy,
                ).start()
            webview.start(
                private_mode=False,
                storage_path=str(data_dir.parent / "webview"),
            )
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        raise SystemExit(run())
    except Exception as exc:
        log_file = write_crash_log(exc)
        try:
            import tkinter.messagebox

            tkinter.messagebox.showerror(
                APP_NAME,
                f"Depth Lab failed to start.\n\nError log: {log_file}",
            )
        except Exception:
            pass
        raise
