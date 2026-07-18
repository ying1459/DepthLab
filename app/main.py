from __future__ import annotations

import multiprocessing
import os
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.depth_engine import MODEL_IDS, ProcessingCancelled, VideoOptions
from app.worker import process_job_worker


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"
JOBS_DIR = Path(os.getenv("DEPTH_LAB_DATA", BASE_DIR / "data" / "jobs"))
JOBS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv"}
MAX_UPLOAD_BYTES = int(os.getenv("DEPTH_LAB_MAX_UPLOAD_MB", "2048")) * 1024 * 1024

app = FastAPI(title="Depth Lab", version="1.0.2")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
worker_context = multiprocessing.get_context("spawn")


@dataclass
class Job:
    id: str
    filename: str
    source_path: Path
    output_path: Path
    options: VideoOptions
    state: str = "queued"
    progress: float = 0.0
    message: str = "等待处理"
    current_frame: int = 0
    total_frames: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)
    cancel_event: Any = field(default_factory=worker_context.Event, repr=False)

    def public(self) -> dict:
        payload = {
            "id": self.id,
            "filename": self.filename,
            "state": self.state,
            "progress": round(self.progress * 100, 1),
            "message": self.message,
            "current_frame": self.current_frame,
            "total_frames": self.total_frames,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "metadata": self.metadata,
            "options": asdict(self.options),
        }
        if self.state == "completed":
            payload["result_url"] = f"/api/jobs/{self.id}/result"
        return payload


jobs: dict[str, Job] = {}
jobs_lock = threading.RLock()
executor = ThreadPoolExecutor(max_workers=int(os.getenv("DEPTH_LAB_WORKERS", "1")))


def update_job(job: Job, progress: float, message: str, current: int, total: int) -> None:
    with jobs_lock:
        job.progress = progress
        job.message = message
        job.current_frame = current
        job.total_frames = total


def run_job(job: Job) -> None:
    with jobs_lock:
        if job.cancel_event.is_set():
            job.state = "cancelled"
            job.message = "已取消"
            job.finished_at = time.time()
            return
        job.state = "processing"
        job.started_at = time.time()
        job.message = "准备视频"

    progress_queue = worker_context.Queue()
    process = worker_context.Process(
        target=process_job_worker,
        args=(
            str(job.source_path),
            str(job.output_path),
            asdict(job.options),
            progress_queue,
            job.cancel_event,
        ),
        name=f"depth-worker-{job.id[:8]}",
        daemon=True,
    )

    try:
        process.start()
        final_message: dict | None = None
        while True:
            if job.cancel_event.is_set():
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
                raise ProcessingCancelled()
            try:
                message = progress_queue.get(timeout=0.2)
            except queue.Empty:
                if not process.is_alive():
                    break
                continue

            if message.get("kind") == "progress":
                update_job(
                    job,
                    float(message["progress"]),
                    str(message["message"]),
                    int(message["current"]),
                    int(message["total"]),
                )
                continue
            final_message = message
            break

        process.join(timeout=10)
        if final_message is None:
            raise RuntimeError(f"Depth 处理进程意外退出（代码 {process.exitcode}）")
        if final_message.get("kind") == "cancelled":
            raise ProcessingCancelled()
        if final_message.get("kind") == "failed":
            raise RuntimeError(str(final_message.get("error") or "Depth 处理失败"))
        if final_message.get("kind") != "completed":
            raise RuntimeError("Depth 处理进程返回了未知状态")

        metadata = dict(final_message["metadata"])
        with jobs_lock:
            job.state = "completed"
            job.progress = 1.0
            job.message = "处理完成"
            job.metadata = metadata
            job.finished_at = time.time()
    except ProcessingCancelled:
        job.output_path.unlink(missing_ok=True)
        job.output_path.with_name("depth_silent.mp4").unlink(missing_ok=True)
        with jobs_lock:
            job.state = "cancelled"
            job.message = "已取消"
            job.finished_at = time.time()
    except Exception as exc:  # surfaced to the local UI
        job.output_path.unlink(missing_ok=True)
        job.output_path.with_name("depth_silent.mp4").unlink(missing_ok=True)
        with jobs_lock:
            job.state = "failed"
            job.message = "处理失败"
            job.error = str(exc)
            job.finished_at = time.time()
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        progress_queue.close()
        progress_queue.join_thread()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "device": "CPU · 流畅模式",
        "models": list(MODEL_IDS),
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "cpu_threads": int(os.getenv("DEPTH_LAB_CPU_THREADS", "4")),
    }


@app.post("/api/jobs", status_code=202)
async def create_job(
    video: UploadFile = File(...),
    model: str = Form("small"),
    mode: str = Form("depth"),
    palette: str = Form("turbo"),
    max_side: int = Form(512),
    output_fps: float = Form(12),
    smoothing: float = Form(0.82),
    invert: bool = Form(False),
    keep_audio: bool = Form(True),
) -> dict:
    suffix = Path(video.filename or "video.mp4").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "不支持该文件格式")
    if model not in MODEL_IDS:
        raise HTTPException(400, "未知模型")
    if mode not in {"depth", "blend", "side-by-side"}:
        raise HTTPException(400, "未知输出模式")
    if palette not in {"gray", "turbo", "inferno", "viridis", "magma"}:
        raise HTTPException(400, "未知色板")
    if max_side not in {0, 512, 768, 1024}:
        raise HTTPException(400, "无效分辨率")
    if output_fps not in {0, 12, 24, 30}:
        raise HTTPException(400, "无效输出帧率")

    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True)
    source_path = job_dir / f"source{suffix}"

    size = 0
    try:
        with source_path.open("wb") as target:
            while chunk := await video.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "视频超过上传大小限制")
                target.write(chunk)
    except Exception:
        source_path.unlink(missing_ok=True)
        job_dir.rmdir()
        raise
    finally:
        await video.close()

    if size == 0:
        source_path.unlink(missing_ok=True)
        job_dir.rmdir()
        raise HTTPException(400, "视频文件为空")

    options = VideoOptions(
        model=model,
        mode=mode,
        palette=palette,
        max_side=max_side,
        output_fps=output_fps,
        smoothing=min(0.98, max(0.0, smoothing)),
        invert=invert,
        keep_audio=keep_audio,
    )
    job = Job(
        id=job_id,
        filename=video.filename or f"video{suffix}",
        source_path=source_path,
        output_path=job_dir / "depth_result.mp4",
        options=options,
    )
    with jobs_lock:
        jobs[job_id] = job
    executor.submit(run_job, job)
    return job.public()


def get_job_or_404(job_id: str) -> Job:
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在或服务已重启")
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return get_job_or_404(job_id).public()


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    job = get_job_or_404(job_id)
    if job.state in {"queued", "processing"}:
        job.cancel_event.set()
        with jobs_lock:
            job.message = "正在取消"
    return job.public()


@app.get("/api/jobs/{job_id}/result")
def result(job_id: str) -> FileResponse:
    job = get_job_or_404(job_id)
    if job.state != "completed" or not job.output_path.exists():
        raise HTTPException(409, "结果尚未生成")
    stem = Path(job.filename).stem
    return FileResponse(
        job.output_path,
        media_type="video/mp4",
        filename=f"{stem}_depth.mp4",
        content_disposition_type="attachment",
    )


@app.get("/api/jobs/{job_id}/preview")
def preview(job_id: str) -> FileResponse:
    job = get_job_or_404(job_id)
    if job.state != "completed" or not job.output_path.exists():
        raise HTTPException(409, "结果尚未生成")
    return FileResponse(job.output_path, media_type="video/mp4", content_disposition_type="inline")


@app.on_event("shutdown")
def stop_active_workers() -> None:
    with jobs_lock:
        active_jobs = [job for job in jobs.values() if job.state in {"queued", "processing"}]
    for job in active_jobs:
        job.cancel_event.set()
    executor.shutdown(wait=False, cancel_futures=True)
