"""Offline wire-level checks: real serializers, fixed destinations, no live billing."""

import json

import httpx
import pytest
from backend.src import user_ai
from backend.src.services.ai_providers import ENDPOINTS, AIProvider, endpoint_for
from backend.src.services.user_ai_runtime import UserAIError
from backend.src.user_ai import UserAIConfig, user_ai_session
from pydantic import ValidationError


@pytest.mark.parametrize("provider", list(AIProvider))
def test_real_client_serialization_and_output_for_each_provider(provider, monkeypatch):
    requests = []
    original_openai = user_ai.OpenAI
    original_http = httpx.Client

    def respond(request):
        requests.append(request)
        if provider == "anthropic":
            return httpx.Response(
                200,
                json={
                    "stop_reason": "end_turn",
                    "content": [{"type": "text", "text": '{"ok":true}'}],
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "offline",
                "object": "chat.completion",
                "created": 0,
                "model": "account-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"ok":true}'},
                    }
                ],
            },
        )

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        user_ai,
        "OpenAI",
        lambda **kw: original_openai(
            **kw,
            http_client=original_http(transport=transport),
        ),
    )
    # Native Claude transport, without mocking its protocol conversion.
    if provider == "anthropic":
        monkeypatch.setattr(httpx, "Client", lambda **kw: original_http(**kw, transport=transport))
    monkeypatch.setenv("OPENAI_BASE_URL", "https://untrusted.invalid/v1")
    config = UserAIConfig(provider=provider, model="account-model", api_key="offline-secret")
    with user_ai_session(config, required=True) as runtime:
        result = runtime.create(
            model="ignored-model",
            temperature=0.0,
            messages=[
                {"role": "system", "content": "Return JSON."},
                {"role": "user", "content": "Extract the metadata."},
            ],
            response_format={"type": "json_object"},
        )
        assert json.loads(result.choices[0].message.content) == {"ok": True}
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url).startswith(endpoint_for(provider) + "/")
    assert "offline-secret" not in str(request.url)
    body = json.loads(request.content)
    assert body["model"] == "account-model"
    if provider == "anthropic":
        assert request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == "offline-secret"
        assert "response_format" not in body and "temperature" not in body
        assert "JSON" in body["system"] and body["max_tokens"] == 4096
        assert all(m["role"] == "user" for m in body["messages"])
    else:
        assert request.headers["authorization"] == "Bearer offline-secret"
    if provider == "minimax":
        assert "response_format" not in body
        assert "JSON" in body["messages"][-1]["content"]
    if provider == "openrouter":
        assert body["provider"]["require_parameters"] is True


@pytest.mark.parametrize("provider,regions", list(ENDPOINTS.items()))
def test_region_defaults_and_explicit_presets(provider, regions):
    assert endpoint_for(provider) == next(iter(regions.values()))
    for region, endpoint in regions.items():
        config = UserAIConfig(provider=provider, region=region, model="m", api_key="k")
        assert endpoint_for(config.provider, config.region) == endpoint
    with pytest.raises(ValidationError):
        UserAIConfig(provider=provider, region="untrusted.invalid", model="m", api_key="k")


def test_qwen_workspace_cannot_escape_official_host():
    config = UserAIConfig(
        provider="qwen",
        region="singapore",
        workspace="workspace123",
        model="qwen3",
        api_key="k",
    )
    assert endpoint_for(config.provider, config.region, config.workspace) == (
        "https://workspace123.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    )
    for workspace in ["bad.host", "user@host", "../../host", "id/path", "-bad", "bad-"]:
        with pytest.raises(ValidationError):
            UserAIConfig(provider="qwen", workspace=workspace, model="m", api_key="k")
    with pytest.raises(ValidationError):
        UserAIConfig(provider="openai", workspace="id", model="m", api_key="k")


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "AI_AUTH_FAILED"),
        (403, "AI_ACCESS_DENIED"),
        (429, "AI_RATE_LIMITED"),
        (404, "AI_MODEL_UNAVAILABLE"),
        (500, "AI_PROVIDER_FAILED"),
    ],
)
def test_native_claude_errors_are_safe_and_not_retried(monkeypatch, status, code):
    original = httpx.Client
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, text="secret-key upstream-private-body")

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(
            **kw,
            transport=httpx.MockTransport(respond),
        ),
    )
    config = UserAIConfig(provider="anthropic", model="m", api_key="secret-key")
    with user_ai_session(config) as runtime:
        with pytest.raises(UserAIError) as error:
            runtime.create(messages=[{"role": "user", "content": "JSON"}])
        assert error.value.code == code
        assert "secret-key" not in str(error.value)
        assert "upstream-private-body" not in str(error.value)
        with pytest.raises(UserAIError):
            runtime.create(messages=[])
    assert len(calls) == 1


@pytest.mark.parametrize("reason", ["max_tokens", "tool_use", "refusal", None])
def test_native_claude_incomplete_response_is_never_accepted(monkeypatch, reason):
    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(
            **kw,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "stop_reason": reason,
                        "content": [{"type": "text", "text": '{"verdict":"SUPPORT"}'}],
                    },
                )
            ),
        ),
    )
    config = UserAIConfig(provider="anthropic", model="m", api_key="k")
    with user_ai_session(config) as runtime:
        with pytest.raises(UserAIError):
            runtime.create(messages=[{"role": "user", "content": "JSON"}])


def test_qwen_reasoning_parameter_and_original_messages_are_isolated():
    from backend.src.services.ai_providers import prepare_completion

    original = {"temperature": 0, "messages": [{"role": "user", "content": "JSON"}]}
    adapted = prepare_completion("qwen", "qwen3-plus", original)
    assert adapted["extra_body"]["enable_thinking"] is False
    assert "temperature" not in adapted
    adapted["messages"][0]["content"] = "changed"
    assert original["messages"][0]["content"] == "JSON"


@pytest.mark.parametrize("finish", ["length", "content_filter", "tool_calls"])
def test_partial_openai_compatible_generation_cannot_be_a_verdict(finish):
    from types import SimpleNamespace

    from backend.src.services.ai_providers import normalize_completion

    result = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish,
                message=SimpleNamespace(content='{"verdict":"SUPPORT"}'),
            )
        ]
    )
    with pytest.raises(ValueError):
        normalize_completion("openai", result)


def test_minimax_reasoning_is_removed_without_rewriting_the_json_answer():
    from types import SimpleNamespace

    from backend.src.services.ai_providers import normalize_completion

    answer = '{"rationale":"Keep <think> inside JSON unchanged."}'
    result = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="<think>private reasoning</think>" + answer),
            )
        ]
    )
    assert normalize_completion("minimax", result).choices[0].message.content == answer


def test_native_http_timeout_has_safe_stable_error():
    from backend.src.services.user_ai_runtime import safe_provider_error

    error = safe_provider_error(httpx.ReadTimeout("secret-key request details"))
    assert error.code == "AI_TIMEOUT"
    assert "secret-key" not in str(error)
