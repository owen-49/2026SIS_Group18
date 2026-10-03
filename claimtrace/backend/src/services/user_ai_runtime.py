"""Request-owned AI invocation boundary, independent of API transport."""

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


class UserAIError(RuntimeError):
    """An upstream failure represented without provider payloads or secrets."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def safe_provider_error(exc: Exception) -> UserAIError:
    status = getattr(exc, "status_code", None)
    name = type(exc).__name__
    if status == 401:
        return UserAIError("AI_AUTH_FAILED", "The user's AI credentials were rejected.")
    if status == 403:
        return UserAIError("AI_ACCESS_DENIED", "The user's AI account cannot access this resource.")
    if status == 429:
        # Inspect only the structured code; never expose the provider's body.
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            error = body.get("error", body)
            code = error.get("code") if isinstance(error, dict) else None
            if code in {"insufficient_quota", "quota_exceeded"}:
                return UserAIError("AI_QUOTA_EXCEEDED", "The user's AI quota is exhausted.")
        return UserAIError("AI_RATE_LIMITED", "The user's AI provider rate limited the request.")
    if status == 404:
        return UserAIError("AI_MODEL_UNAVAILABLE", "The requested AI model is unavailable.")
    if isinstance(exc, TimeoutError) or name == "APITimeoutError":
        return UserAIError("AI_TIMEOUT", "The user's AI provider did not respond in time.")
    return UserAIError("AI_PROVIDER_FAILED", "The user's AI provider could not complete the call.")


@dataclass(repr=False)
class UserAIRuntime:
    """One request's client and model; never placed in application state.

    Wrapping completions at this boundary keeps SDK exception payloads away
    from Engine rationale and persisted reference diagnostics. Existing Engine
    entry points can continue using client.chat.completions.create unchanged.
    """

    raw_client: Any = field(repr=False)
    model: str
    timeout_seconds: float = 30.0
    failure: UserAIError | None = field(default=None, init=False, repr=False)

    @property
    def chat(self):
        return SimpleNamespace(completions=self)

    def create(self, **kwargs):
        if self.failure is not None:
            raise self.failure from None
        kwargs["model"] = self.model
        kwargs["timeout"] = self.timeout_seconds
        try:
            return self.raw_client.chat.completions.create(**kwargs)
        except Exception as exc:
            self.failure = safe_provider_error(exc)
            raise self.failure from None

    def raise_if_failed(self) -> None:
        if self.failure is not None:
            raise self.failure from None

    def close(self) -> None:
        self.raw_client.close()
