"""Shared backend API test fixtures."""

import os

import fitz
import pytest

# Opt out of the repository .env *before* importing the application: main.py
# builds its CORS middleware from settings at import time, so a developer's
# CORS_ORIGINS would otherwise be baked into the app under test. This must run
# at collection time, not in a fixture.
os.environ["CLAIMTRACE_ENV_FILE"] = os.devnull

from backend.src.config import get_settings  # noqa: E402
from backend.src.main import app  # noqa: E402
from backend.src.routes import parse as parse_route  # noqa: E402
from backend.src.services import engine_adapter, paper_deletion_service  # noqa: E402
from backend.src.storage import (  # noqa: E402
    bib_document_store,
    paper_store,
    parsed_document_store,
)
from fastapi.testclient import TestClient  # noqa: E402


def _clear_settings_caches() -> None:
    """Drop the cached settings, LLM client and embedder.

    These may have been replaced by a test with a plain callable (which has no
    ``cache_clear``), and monkeypatch only restores them after this fixture tears
    down, so the attribute must be probed defensively. Dropping the embedder also
    keeps the ~90MB sentence-transformers model out of a suite that never needs
    a real one.
    """
    get_settings.cache_clear()
    for cached in (engine_adapter._get_llm_client, engine_adapter._get_embedder):
        cache_clear = getattr(cached, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch):
    """Keep the suite hermetic and offline.

    ``config._load_settings`` loads the repository ``.env``, so without this a
    developer machine would hand tests real CORS origins, upload paths and API
    keys — changing assertions and risking calls to a paid provider. The module
    level above already opts out of ``.env`` for the import-time CORS middleware;
    here the provider is neutralised so the LLM fallback paths stay the ones
    under test, and the caches are dropped so each test re-reads the environment.
    """
    for name in (
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAIMTRACE_LLM_PROVIDER", "openai")

    _clear_settings_caches()
    yield
    _clear_settings_caches()


@pytest.fixture()
def storage_paths(tmp_path, monkeypatch):
    """Point file and JSON persistence at an isolated test directory."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    papers_file = upload_dir / "papers.json"
    parsed_dir = tmp_path / "parsed"
    bib_parsed_dir = parsed_dir / "bib"

    monkeypatch.setattr(parse_route, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(paper_deletion_service, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(paper_store, "PAPERS_FILE", papers_file)
    monkeypatch.setattr(parsed_document_store, "PARSED_DIR", parsed_dir)
    monkeypatch.setattr(bib_document_store, "BIB_PARSED_DIR", bib_parsed_dir)

    return {
        "upload_dir": upload_dir,
        "papers_file": papers_file,
        "parsed_dir": parsed_dir,
        "bib_parsed_dir": bib_parsed_dir,
    }


@pytest.fixture()
def sample_pdf_bytes():
    """Return a valid two-page PDF for Parser-backed API tests."""
    document = fitz.open()
    first_page = document.new_page()
    first_page.insert_text((72, 72), "1 Introduction", fontsize=20)
    first_page.insert_text(
        (72, 115),
        "Self-attention enables the model to relate information from different positions "
        "without recurrence.",
        fontsize=11,
    )
    second_page = document.new_page()
    second_page.insert_text((72, 72), "2 Methods", fontsize=20)
    second_page.insert_text(
        (72, 115),
        "The experiment evaluates citation verification quality using source passages.",
        fontsize=11,
    )
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


@pytest.fixture()
def client(storage_paths, monkeypatch):
    """Return an API client using isolated local persistence."""
    del storage_paths

    with TestClient(app) as test_client:
        monkeypatch.delattr(app.state, "bibliography_lookup", raising=False)
        yield test_client
