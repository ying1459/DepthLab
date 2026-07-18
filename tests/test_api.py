from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_index_is_available() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Depth Lab" in response.text


def test_health_reports_models() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "small" in payload["models"]


def test_rejects_unsupported_file() -> None:
    response = client.post(
        "/api/jobs",
        files={"video": ("notes.txt", b"not a video", "text/plain")},
    )
    assert response.status_code == 400


def test_static_assets_exist() -> None:
    static_dir = Path(__file__).parents[1] / "app" / "static"
    assert (static_dir / "styles.css").exists()
    assert (static_dir / "app.js").exists()
