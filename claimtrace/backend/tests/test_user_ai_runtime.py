"""Secret handling and concurrency tests for the user-owned AI boundary."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest
from backend.src.services.user_ai_runtime import UserAIError, UserAIRuntime


def client(create):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (401, None, "AI_AUTH_FAILED"),
        (403, None, "AI_ACCESS_DENIED"),
        (429, {"error": {"code": "insufficient_quota"}}, "AI_QUOTA_EXCEEDED"),
        (429, None, "AI_RATE_LIMITED"),
        (404, None, "AI_MODEL_UNAVAILABLE"),
        (500, None, "AI_PROVIDER_FAILED"),
    ],
)
def test_sdk_payload_cannot_reach_engine_or_reference_diagnostics(status, body, expected):
    upstream = RuntimeError("secret-user-key and provider-private-body")
    upstream.status_code = status
    upstream.body = body

    def fail(**kwargs):
        raise upstream

    runtime = UserAIRuntime(client(fail), "user-model")
    with pytest.raises(UserAIError) as caught:
        runtime.chat.completions.create(model="team-model")
    assert caught.value.code == expected
    assert "secret-user-key" not in repr(caught.value)
    assert "provider-private-body" not in repr(caught.value)
    with pytest.raises(UserAIError):
        runtime.raise_if_failed()


def test_timeout_has_stable_safe_error():
    def fail(**kwargs):
        raise TimeoutError("private request")

    with pytest.raises(UserAIError) as caught:
        UserAIRuntime(client(fail), "user-model").create()
    assert caught.value.code == "AI_TIMEOUT"


def test_concurrent_users_keep_clients_models_and_failures_isolated():
    barrier = Barrier(2)

    def run(user):
        def create(**kwargs):
            barrier.wait(timeout=5)
            return user, kwargs

        runtime = UserAIRuntime(client(create), f"{user}-model")
        result = runtime.create(model="team-model", timeout=600)
        assert runtime.failure is None
        return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        outputs = list(executor.map(run, ["alice", "bob"]))
    assert outputs == [
        ("alice", {"model": "alice-model", "timeout": 30.0}),
        ("bob", {"model": "bob-model", "timeout": 30.0}),
    ]
