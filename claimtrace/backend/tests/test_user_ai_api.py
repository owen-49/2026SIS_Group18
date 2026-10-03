"""Real route/service integration with offline per-user provider clients."""

import json
from types import SimpleNamespace

import pytest
from backend.src import user_ai
from backend.src.main import app
from backend.src.services import citation_comparison_service, reference_input_service
from backend.src.storage.reference_store import reference_path
from backend.tests.test_bibliography_audit import (
    FakeLookup,
    lookup_result,
    persist_manuscript,
)
from backend.tests.test_citation_comparison_api import (
    CLAIM,
    MARKER,
    SUPPORT_REPLY,
    FakeRetriever,
    seeded,  # noqa: F401 imported pytest fixture
)

CONFIG = {"provider": "openai", "model": "user-model", "api_key": "private-user-key"}


@pytest.fixture
def providers(monkeypatch):
    clients = []

    def build(**config):
        calls = []
        owner = SimpleNamespace(config=config, calls=calls, reply=SUPPORT_REPLY, closed=False)

        def create(**kwargs):
            calls.append(kwargs)
            if isinstance(owner.reply, Exception):
                raise owner.reply
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=owner.reply))]
            )

        def close():
            owner.closed = True

        owner.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        owner.close = close
        clients.append(owner)
        return owner

    monkeypatch.setattr(user_ai, "OpenAI", build)
    monkeypatch.setattr(citation_comparison_service, "_new_retriever", FakeRetriever)
    return clients


@pytest.mark.usefixtures("seeded")
def test_verify_uses_user_key_model_and_official_url_despite_team_environment(
    client, providers, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "team-key-must-not-be-used")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://untrusted.invalid/v1")
    response = client.post(
        "/api/verify/citation",
        json={
            "claim": CLAIM,
            "citation_marker": MARKER,
            "ai_config": CONFIG,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "COMPARED"
    provider = providers[0]
    assert provider.config == {
        "api_key": "private-user-key",
        "base_url": "https://api.openai.com/v1",
        "timeout": 30.0,
        "max_retries": 0,
    }
    assert provider.calls[0]["model"] == "user-model"
    assert provider.calls[0]["timeout"] == 30.0
    assert provider.closed
    assert "private-user-key" not in response.text


@pytest.mark.parametrize("endpoint", ["/api/verify/citation", "/api/verify"])
def test_missing_user_config_never_uses_team_key(client, providers, monkeypatch, endpoint):
    monkeypatch.setenv("OPENAI_API_KEY", "team-key-must-not-be-used")
    response = client.post(
        endpoint,
        json={
            "claim": CLAIM,
            "citation_marker": MARKER,
            "source_paper_id": "source",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "AI_CONFIG_REQUIRED"
    assert providers == []


@pytest.mark.parametrize(
    "changes",
    [
        {"api_key": ""},
        {"provider": "unsupported"},
        {"model": "   "},
        {"base_url": "https://untrusted.invalid/v1"},
        {"api_key": {"secret": "private-user-key"}},
    ],
)
def test_validation_errors_never_echo_keys(client, providers, changes):
    response = client.post(
        "/api/verify/citation",
        json={
            "claim": CLAIM,
            "citation_marker": MARKER,
            "ai_config": {**CONFIG, **changes},
        },
    )
    assert response.status_code == 422
    assert "private-user-key" not in response.text
    assert providers == []


@pytest.mark.usefixtures("seeded")
def test_provider_auth_failure_is_safe_and_never_falls_back(client, providers, monkeypatch):
    original = user_ai.OpenAI

    def build(**config):
        provider = original(**config)
        error = RuntimeError("private-user-key leaked in SDK payload")
        error.status_code = 401
        provider.reply = error
        return provider

    monkeypatch.setattr(user_ai, "OpenAI", build)
    response = client.post(
        "/api/verify/citation",
        json={
            "claim": CLAIM,
            "citation_marker": MARKER,
            "ai_config": CONFIG,
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AI_AUTH_FAILED"
    assert "private-user-key" not in response.text
    assert len(providers) == 1 and len(providers[0].calls) == 1 and providers[0].closed


def test_reference_segmentation_uses_user_config_and_cache_contains_no_key(
    client, storage_paths, providers, monkeypatch
):
    manuscript = persist_manuscript(storage_paths)
    raw = "Journal of Retrieval, 2024. J. Smith. Retrieval with citations."
    monkeypatch.setattr(
        reference_input_service,
        "extract_pdf_references",
        lambda path: SimpleNamespace(
            references=[SimpleNamespace(raw_text=raw, number=1, page_start=1, page_end=1)],
            warnings=[],
        ),
    )
    original = user_ai.OpenAI

    def build(**config):
        provider = original(**config)
        provider.reply = json.dumps(
            {
                "items": [
                    {
                        "item_id": "0",
                        "authors": ["J. Smith"],
                        "title": "Retrieval with citations",
                        "venue": "Journal of Retrieval",
                        "year": 2024,
                        "doi": None,
                    }
                ]
            }
        )
        return provider

    monkeypatch.setattr(user_ai, "OpenAI", build)
    monkeypatch.setattr(
        app.state, "bibliography_lookup", FakeLookup(lookup_result("not_found")), raising=False
    )
    config = {**CONFIG, "provider": "deepseek", "model": "deepseek-chat"}
    first = client.post(
        "/api/audit", json={"manuscript_id": manuscript.paper_id, "ai_config": config}
    )
    assert first.status_code == 200
    saved = reference_path(manuscript.paper_id).read_text(encoding="utf-8")
    assert "private-user-key" not in saved and '"SEGMENTED"' in saved
    assert providers[0].config["base_url"] == "https://api.deepseek.com/v1"
    assert providers[0].calls[0]["model"] == "deepseek-chat"
    second = client.post("/api/audit", json={"manuscript_id": manuscript.paper_id})
    assert second.status_code == 200
    assert len(providers) == 1 and len(providers[0].calls) == 1
    assert "private-user-key" not in first.text


def test_claim_discovery_without_config_cannot_consume_team_credits(client, providers, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "team-key-must-not-be-used")
    from backend.src.services.reference_metadata_segmenter import segment_with_user_ai

    outcomes = segment_with_user_ai(["A nonstandard reference"])
    assert outcomes[0].status.value == "NO_CLIENT"
    assert providers == []


def test_configuration_is_excluded_from_request_serialisation():
    from backend.src.models import AuditRequest

    request = AuditRequest(manuscript_id="paper", ai_config=CONFIG)
    assert "private-user-key" not in repr(request)
    assert "ai_config" not in request.model_dump()


@pytest.mark.usefixtures("seeded")
def test_verify_reference_resolution_and_judgement_share_the_user_runtime(
    client, storage_paths, providers, monkeypatch
):
    manuscript = persist_manuscript(storage_paths)
    raw = "Journal of Retrieval, 2024. Smith, Jane. Retrieval with citations. doi: 10.1234/example"
    monkeypatch.setattr(
        reference_input_service,
        "extract_pdf_references",
        lambda path: SimpleNamespace(
            references=[SimpleNamespace(raw_text=raw, number=7, page_start=1, page_end=1)],
            warnings=[],
        ),
    )
    original = user_ai.OpenAI

    def build(**config):
        provider = original(**config)

        def create(**kwargs):
            provider.calls.append(kwargs)
            reply = SUPPORT_REPLY
            if len(kwargs["messages"]) == 2:
                reply = json.dumps(
                    {
                        "items": [
                            {
                                "item_id": "0",
                                "authors": ["Smith, Jane"],
                                "title": "Retrieval with citations",
                                "venue": "Journal of Retrieval",
                                "year": 2024,
                                "doi": "10.1234/example",
                            }
                        ]
                    }
                )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=reply))]
            )

        provider.chat.completions.create = create
        return provider

    monkeypatch.setattr(user_ai, "OpenAI", build)
    response = client.post(
        "/api/verify/citation",
        json={
            "claim": CLAIM,
            "citation_marker": "[7]",
            "manuscript_id": manuscript.paper_id,
            "ai_config": CONFIG,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "COMPARED"
    assert len(providers) == 1
    assert [call["model"] for call in providers[0].calls] == ["user-model", "user-model"]
    assert providers[0].config["api_key"] == CONFIG["api_key"]
    assert providers[0].closed


def test_failed_reference_ai_call_preserves_parser_artifact_for_new_user_request(
    client, storage_paths, providers, monkeypatch
):
    manuscript = persist_manuscript(storage_paths)
    extracted = []
    raw = "Journal of Retrieval, 2024. J. Smith. Retrieval with citations."

    def extract(path):
        extracted.append(path)
        return SimpleNamespace(
            references=[SimpleNamespace(raw_text=raw, number=1, page_start=1, page_end=1)],
            warnings=[],
        )

    monkeypatch.setattr(reference_input_service, "extract_pdf_references", extract)
    original = user_ai.OpenAI

    def build(**config):
        provider = original(**config)
        if len(providers) == 1:
            error = RuntimeError("private-user-key leaked SDK content")
            error.status_code = 401
            provider.reply = error
        else:
            provider.reply = json.dumps(
                {
                    "items": [
                        {
                            "item_id": "0",
                            "authors": ["J. Smith"],
                            "title": "Retrieval with citations",
                            "venue": "Journal of Retrieval",
                            "year": 2024,
                            "doi": None,
                        }
                    ]
                }
            )
        return provider

    monkeypatch.setattr(user_ai, "OpenAI", build)
    monkeypatch.setattr(
        app.state, "bibliography_lookup", FakeLookup(lookup_result("not_found")), raising=False
    )
    first = client.post(
        "/api/audit", json={"manuscript_id": manuscript.paper_id, "ai_config": CONFIG}
    )
    assert first.status_code == 401
    saved = reference_path(manuscript.paper_id).read_text(encoding="utf-8")
    assert '"MODEL_ERROR"' in saved and "private-user-key" not in saved
    second = client.post(
        "/api/audit",
        json={
            "manuscript_id": manuscript.paper_id,
            "ai_config": {**CONFIG, "api_key": "second-user-key"},
        },
    )
    assert second.status_code == 200
    assert len(extracted) == 1
    assert [provider.config["api_key"] for provider in providers] == [
        "private-user-key",
        "second-user-key",
    ]
    assert all(provider.closed for provider in providers)


@pytest.mark.parametrize("failed_status", ["NO_CLIENT", "MODEL_ERROR", "INVALID_RESPONSE"])
def test_retry_preserves_successful_metadata_without_venue(
    client, storage_paths, providers, monkeypatch, failed_status
):
    from pathlib import Path

    from backend.src.storage.reference_store import (
        StoredReference,
        StoredReferenceList,
        load_references,
        save_references,
    )

    manuscript = persist_manuscript(storage_paths)
    successful = StoredReference(
        raw_text="J. Smith. Cached title.",
        title="Cached title",
        authors=["J. Smith"],
        metadata_status="SEGMENTED",
        metadata_source="llm_segmentation",
        metadata_model="cached-model",
    )
    failed = StoredReference(
        raw_text="J. Smith. Retry title. Journal of Retrieval, 2024.",
        metadata_status=failed_status,
    )
    save_references(
        manuscript.paper_id,
        StoredReferenceList(
            paper_id=manuscript.paper_id,
            source_file=Path(manuscript.file_path).name,
            metadata_version=3,
            references=[successful, failed],
        ),
    )
    original = user_ai.OpenAI

    def build(**config):
        provider = original(**config)
        provider.reply = json.dumps(
            {
                "items": [
                    {
                        "item_id": "0",
                        "authors": ["J. Smith"],
                        "title": "Retry title",
                        "venue": "Journal of Retrieval",
                        "year": 2024,
                        "doi": None,
                    }
                ]
            }
        )
        return provider

    monkeypatch.setattr(user_ai, "OpenAI", build)
    monkeypatch.setattr(
        app.state, "bibliography_lookup", FakeLookup(lookup_result("not_found")), raising=False
    )
    for _ in range(2):
        response = client.post(
            "/api/audit", json={"manuscript_id": manuscript.paper_id, "ai_config": CONFIG}
        )
        assert response.status_code == 200
    assert sum(len(provider.calls) for provider in providers) == 1
    assert successful.raw_text not in providers[0].calls[0]["messages"][-1]["content"]
    assert failed.raw_text in providers[0].calls[0]["messages"][-1]["content"]
    assert (
        load_references(manuscript.paper_id).references[0].model_dump() == successful.model_dump()
    )
    assert all(provider.closed for provider in providers)


@pytest.mark.usefixtures("seeded")
def test_deepseek_insufficient_balance_returns_safe_quota_error(client, providers, monkeypatch):
    import httpx
    from openai import APIStatusError

    original = user_ai.OpenAI

    def build(**config):
        provider = original(**config)
        provider.reply = APIStatusError(
            "private-user-key upstream body",
            response=httpx.Response(
                402, request=httpx.Request("POST", "https://api.deepseek.com/chat/completions")
            ),
            body={"error": {"message": "private-user-key"}},
        )
        return provider

    monkeypatch.setattr(user_ai, "OpenAI", build)
    response = client.post(
        "/api/verify/citation",
        json={
            "claim": CLAIM,
            "citation_marker": MARKER,
            "ai_config": {**CONFIG, "provider": "deepseek", "model": "deepseek-chat"},
        },
    )
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "AI_QUOTA_EXCEEDED"
    assert "private-user-key" not in response.text
    assert len(providers[0].calls) == 1 and providers[0].closed


def test_audit_warning_explains_missing_user_configuration(
    client, storage_paths, providers, monkeypatch
):
    manuscript = persist_manuscript(storage_paths)
    monkeypatch.setattr(
        reference_input_service,
        "extract_pdf_references",
        lambda path: SimpleNamespace(
            references=[
                SimpleNamespace(
                    raw_text="An incomplete reference", number=1, page_start=1, page_end=1
                )
            ],
            warnings=[],
        ),
    )
    monkeypatch.setattr(
        app.state, "bibliography_lookup", FakeLookup(lookup_result("not_found")), raising=False
    )
    monkeypatch.setenv("OPENAI_API_KEY", "team-key-must-not-be-used")
    response = client.post("/api/audit", json={"manuscript_id": manuscript.paper_id})
    assert response.status_code == 200
    assert "ai_config" in str(response.json()["warnings"])
    assert providers == []
