from types import SimpleNamespace

from app.launcher import DesktopApi
from app.main import jobs, jobs_lock


class FakeWindow:
    def __init__(self, target: str) -> None:
        self.target = target

    def create_file_dialog(self, *args, **kwargs):
        return (self.target,)


def test_desktop_api_saves_completed_result(tmp_path) -> None:
    source = tmp_path / "generated.mp4"
    target = tmp_path / "saved.mp4"
    source.write_bytes(b"depth-video")
    job_id = "desktop-save-test"
    job = SimpleNamespace(
        state="completed",
        output_path=source,
        filename="sample.mp4",
    )
    with jobs_lock:
        jobs[job_id] = job

    try:
        api = DesktopApi()
        api.attach_window(FakeWindow(str(target)))
        result = api.save_result(job_id)
    finally:
        with jobs_lock:
            jobs.pop(job_id, None)

    assert result == {"ok": True, "path": str(target)}
    assert target.read_bytes() == b"depth-video"
