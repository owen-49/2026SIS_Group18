"""Offline connection checks through the same adapters used for Verify."""

import json

import httpx
import pytest
from backend.src import user_ai
from backend.src.services.ai_providers import ENDPOINTS

SECRET = "private-connection-test-key"
CONFIG = {"provider": "openai", "model": "text-chat", "api_key": SECRET}


@pytest.fixture
def upstream(monkeypatch):
    original = httpx.Client
    requests = []
    state = {"status": 200, "body": {"data": [{"id": "text-chat"}]}, "timeout": False}

    def respond(request):
        requests.append(request)
        assert request.url.host not in {"untrusted.invalid", "team.invalid"}
        if state["timeout"]:
            raise httpx.ReadTimeout(SECRET + " private provider body")
        return httpx.Response(state["status"], json=state["body"])

    transport = httpx.MockTransport(respond)
    constructor = user_ai.OpenAI
    constructors = []

    def build(**kwargs):
        constructors.append(kwargs.copy())
        return constructor(**kwargs, http_client=original(transport=transport))

    monkeypatch.setattr(user_ai, "OpenAI", build)
    # Native Anthropic traffic uses the same entirely offline transport.
    native_constructor = user_ai.AnthropicMessagesClient

    def native(**kwargs):
        instance = native_constructor(**kwargs)
        instance._http.close()
        instance._http = original(
            base_url=kwargs["base_url"] + "/",
            timeout=30.0,
            follow_redirects=False,
            headers={"x-api-key": kwargs["api_key"], "anthropic-version": "2023-06-01"},
            transport=transport,
        )
        return instance

    monkeypatch.setattr(user_ai, "AnthropicMessagesClient", native)
    monkeypatch.setenv("OPENAI_API_KEY", "team-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://team.invalid/v1")
    return state, requests, constructors


def completion(content='{"ok": true}', finish="stop"):
    return {
        "id": "offline",
        "object": "chat.completion",
        "created": 0,
        "model": "text-chat",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {"role": "assistant", "content": content},
            }
        ],
    }


@pytest.mark.parametrize("provider", ENDPOINTS)
def test_models_only_use_official_endpoints_without_retries(client, upstream, provider):
    state, requests, constructors = upstream
    state["body"] = {"data": [{"id": "z-chat"}, {"id": "a-chat"}]}
    response = client.post("/api/ai/models", json={"provider": provider, "api_key": SECRET})
    assert response.status_code == 200
    assert response.json() == {"supported": True, "models": [{"id": "a-chat"}, {"id": "z-chat"}]}
    assert len(requests) == 1
    assert (
        str(requests[0].url).split("?")[0] == next(iter(ENDPOINTS[provider].values())) + "/models"
    )
    assert requests[0].method == "GET"
    if provider != "anthropic":
        assert constructors[0]["max_retries"] == 0
        assert constructors[0]["timeout"] == 30.0
    assert SECRET not in response.text


def test_models_filter_sort_limit_and_drop_secret_echo(client, upstream):
    state, _, _ = upstream
    ids = [
        "text-embedding-3",
        "tts-1",
        "whisper-1",
        "dall-e-3",
        "omni-moderation",
        "image-gen",
        "audio-gen",
        "rerank-v3",
        SECRET,
        "bad\nmodel",
        "chat-vision",
    ]
    ids += [f"chat-{n:03d}" for n in range(600)] + ["chat-000"]
    state["body"] = {"data": [{"id": value} for value in ids]}
    response = client.post("/api/ai/models", json={"provider": "openai", "api_key": SECRET})
    assert response.json()["models"] == [{"id": f"chat-{n:03d}"} for n in range(500)]
    assert SECRET not in response.text


@pytest.mark.parametrize("status", [404, 405])
@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_models_unsupported_is_not_an_error(client, upstream, status, provider):
    state, requests, _ = upstream
    state.update(status=status, body={"error": {"message": SECRET}})
    response = client.post("/api/ai/models", json={"provider": provider, "api_key": SECRET})
    assert response.json() == {"supported": False, "models": []}
    assert len(requests) == 1


@pytest.mark.parametrize("path", ["/api/ai/models", "/api/ai/test"])
@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize(
    "status,structured,code,http_status",
    [
        (401, {}, "AI_AUTH_FAILED", 401),
        (403, {}, "AI_ACCESS_DENIED", 403),
        (429, {}, "AI_RATE_LIMITED", 429),
        (429, {"code": "insufficient_quota"}, "AI_QUOTA_EXCEEDED", 429),
        (400, {"code": "model_not_found"}, "AI_MODEL_UNAVAILABLE", 422),
        (400, {"type": "model_not_exist"}, "AI_MODEL_UNAVAILABLE", 422),
        (400, {"code": "invalid_request_error"}, "AI_REQUEST_REJECTED", 422),
        (400, {"code": [SECRET]}, "AI_REQUEST_REJECTED", 422),
        (500, {}, "AI_PROVIDER_FAILED", 502),
    ],
)
def test_safe_failures_do_not_echo_or_retry(
    client, upstream, caplog, path, provider, status, structured, code, http_status
):
    state, requests, _ = upstream
    state.update(
        status=status, body={"error": {**structured, "message": SECRET + " provider-private"}}
    )
    config = {**CONFIG, "provider": provider}
    if path.endswith("models"):
        config.pop("model")
    response = client.post(path, json=config)
    assert response.status_code == http_status
    assert response.json()["detail"]["code"] == code
    assert SECRET not in response.text + caplog.text
    assert "provider-private" not in response.text + caplog.text
    assert len(requests) == 1


@pytest.mark.parametrize("path", ["/api/ai/models", "/api/ai/test"])
@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_timeout_is_safe_without_retry(client, upstream, path, provider):
    state, requests, _ = upstream
    state["timeout"] = True
    config = {**CONFIG, "provider": provider}
    if path.endswith("models"):
        config.pop("model")
    response = client.post(path, json=config)
    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "AI_TIMEOUT"
    assert SECRET not in response.text
    assert len(requests) == 1


@pytest.mark.parametrize("provider", ["openai", "deepseek", "qwen", "minimax", "anthropic"])
def test_connection_uses_verify_normalization_and_json_mode(client, upstream, provider):
    state, requests, constructors = upstream
    content = '<think>reasoning</think>{"ok":true}' if provider == "minimax" else '{"ok":true}'
    state["body"] = completion(content)
    if provider == "anthropic":
        state["body"] = {"stop_reason": "end_turn", "content": [{"type": "text", "text": content}]}
    config = {
        **CONFIG,
        "provider": provider,
        "model": "qwen3-plus" if provider == "qwen" else "text-chat",
    }
    response = client.post("/api/ai/test", json=config)
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["model"] == config["model"]
    assert response.json()["latency_ms"] >= 0
    body = json.loads(requests[0].content)
    if provider not in {"anthropic", "minimax"}:
        assert body["response_format"] == {"type": "json_object"}
    else:
        assert "JSON" in json.dumps(body)
    if provider == "qwen":
        assert body["enable_thinking"] is False
    if provider in {"openai", "deepseek"}:
        assert body["temperature"] == 0.0
    else:
        assert "temperature" not in body
    if constructors:
        assert constructors[0]["max_retries"] == 0
    assert body.get("max_tokens", 4096) >= 4096
    assert SECRET not in response.text


@pytest.mark.parametrize(
    "content,finish",
    [
        ("not JSON", "stop"),
        ('{"ok":true}', "length"),
        ('{"ok":true}', None),
        ("[]", "stop"),
        ('{"ok":false}', "stop"),
        ('{"ok":true}', "tool_calls"),
        (SECRET, "stop"),
    ],
)
def test_incompatible_output_is_safe(client, upstream, content, finish):
    state, _, _ = upstream
    state["body"] = completion(content, finish)
    response = client.post("/api/ai/test", json=CONFIG)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "AI_MODEL_INCOMPATIBLE"
    assert SECRET not in response.text


@pytest.mark.parametrize("path", ["/api/ai/models", "/api/ai/test"])
@pytest.mark.parametrize(
    "extra",
    [
        {"base_url": "https://untrusted.invalid"},
        {"provider": "unknown"},
        {"region": "untrusted.invalid"},
        {"workspace": "../escape"},
        {"api_key": " " + SECRET},
    ],
)
def test_new_routes_sanitize_validation_and_never_fall_back(client, upstream, path, extra):
    _, requests, _ = upstream
    config = {**CONFIG, **extra}
    if path.endswith("models"):
        config.pop("model")
    response = client.post(path, json=config)
    assert response.status_code == 422
    assert SECRET not in response.text
    assert not requests


@pytest.mark.parametrize("path", ["/api/ai/models", "/api/ai/test"])
def test_missing_config_does_not_use_environment_key(client, upstream, path):
    _, requests, _ = upstream
    response = client.post(path, json={})
    assert response.status_code == 422
    assert not requests


def test_models_keep_vision_chat_and_never_follow_next_page(client, upstream):
    state, requests, _ = upstream
    state["body"] = {
        "data": [{"id": "chat-vision"}, {"id": "qwen-vl"}, {"id": "text-chat"}],
        "has_more": True,
        "next": "https://untrusted.invalid/models",
    }
    response = client.post("/api/ai/models", json={"provider": "openai", "api_key": SECRET})
    assert response.json()["models"] == [
        {"id": "chat-vision"},
        {"id": "qwen-vl"},
        {"id": "text-chat"},
    ]
    assert len(requests) == 1
    assert all(value == 30 for value in requests[0].extensions["timeout"].values())


def test_unsupported_protocol_and_client_cleanup(client, monkeypatch):
    from types import SimpleNamespace

    closed = []

    def unsupported():
        raise NotImplementedError(SECRET)

    monkeypatch.setattr(
        user_ai,
        "OpenAI",
        lambda **kwargs: SimpleNamespace(
            models=SimpleNamespace(list=unsupported),
            close=lambda: closed.append(True),
        ),
    )
    response = client.post("/api/ai/models", json={"provider": "openai", "api_key": SECRET})
    assert response.json() == {"supported": False, "models": []}
    assert closed == [True]


def test_model_field_cannot_echo_pasted_key(client, upstream):
    state, _, _ = upstream
    state["body"] = completion()
    response = client.post("/api/ai/test", json={**CONFIG, "model": SECRET})
    assert response.status_code == 200
    assert response.json()["model"] == "[redacted]"
    assert SECRET not in response.text
