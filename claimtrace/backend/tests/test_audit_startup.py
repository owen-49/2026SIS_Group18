"""A fresh local Audit deployment must start before its storage tree exists."""

from dataclasses import replace

from backend.src import main
from fastapi.testclient import TestClient


def test_startup_creates_nested_upload_directory(tmp_path, storage_paths, monkeypatch):
    upload = tmp_path / "fresh" / "nested" / "uploads"
    monkeypatch.setattr(main, "settings", replace(main.settings, upload_dir=upload))
    assert not upload.parent.exists()
    with TestClient(main.app) as client:
        assert upload.is_dir()
        assert client.get("/health").json()["status"] == "ok"
        response = client.post(
            "/api/parse",
            files={
                "file": ("references.bib", b"@article{a, title={Startup acceptance}, year={2024}}")
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
