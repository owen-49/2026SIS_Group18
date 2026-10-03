"""Readiness must detect missing runtime prerequisites without spending tokens."""

import subprocess
from dataclasses import replace
from types import SimpleNamespace

import pytest
from backend.src.config import Settings
from backend.src.routes import health
from backend.src.services import runtime_checks


@pytest.mark.parametrize(
    ("version", "expected"), [("1.8.0_401", False), ("11.0.25", True), ("17.0.13", True)],
)
def test_java_minimum_version(monkeypatch, version, expected):
    monkeypatch.setattr(runtime_checks.shutil, "which", lambda _: "/test/java")
    monkeypatch.setattr(
        runtime_checks.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout="", stderr=f'openjdk version "{version}"',
        ),
    )
    assert runtime_checks._java_available() is expected


def test_java_timeout_is_not_ready(monkeypatch):
    monkeypatch.setattr(runtime_checks.shutil, "which", lambda _: "/test/java")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("java", 5)

    monkeypatch.setattr(runtime_checks.subprocess, "run", timeout)
    assert not runtime_checks._java_available()


def test_fresh_volume_preflight_and_missing_package(tmp_path, monkeypatch):
    settings = replace(
        Settings(), upload_dir=tmp_path / "uploads", papers_file=tmp_path / "uploads/papers.json",
        parsed_dir=tmp_path / "uploads/parsed",
    )
    monkeypatch.setattr(runtime_checks, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime_checks, "_java_available", lambda: True)
    monkeypatch.setattr(runtime_checks.importlib.util, "find_spec", lambda _: object())
    monkeypatch.setenv("HF_HOME", str(tmp_path / "cache"))
    assert not runtime_checks.runtime_checks()["uploads_writable"]
    assert all(runtime_checks.runtime_checks(create_directories=True).values())
    assert list(settings.parsed_dir.iterdir()) == []
    monkeypatch.setattr(
        runtime_checks.importlib.util, "find_spec",
        lambda name: None if name == "faiss" else object(),
    )
    assert not runtime_checks.runtime_checks()["package_faiss"]


def test_readiness_reports_write_failure(tmp_path, monkeypatch):
    def denied(**kwargs):
        raise PermissionError("secret-storage-path")

    monkeypatch.setattr(runtime_checks.tempfile, "TemporaryFile", denied)
    assert not runtime_checks._writable(tmp_path, False)


@pytest.mark.parametrize("ready", [True, False])
def test_readiness_http_status(client, monkeypatch, ready):
    monkeypatch.setattr(health, "runtime_checks", lambda: {"uploads_writable": ready})
    response = client.get("/ready")
    assert response.status_code == (200 if ready else 503)
    assert response.json()["checks"] == {"uploads_writable": ready}
    assert client.get("/health").status_code == 200
