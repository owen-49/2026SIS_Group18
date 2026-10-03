"""User AI configuration, request lifetime and safe API errors."""

from contextlib import contextmanager
from typing import Literal

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from .services.user_ai_runtime import UserAIError, UserAIRuntime


class UserAIConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["openai", "deepseek"]
    model: str = Field(min_length=1, max_length=200)
    api_key: SecretStr = Field(min_length=1, max_length=4096)

    @field_validator("model")
    @classmethod
    def model_has_text(cls, value):
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("Provide a nonempty model without control characters.")
        return value.strip()

    @field_validator("api_key")
    @classmethod
    def key_has_text(cls, value):
        key = value.get_secret_value()
        if not key.strip() or key != key.strip() or any(ord(char) < 33 for char in key):
            raise ValueError("Provide an API key without whitespace or control characters.")
        return value


@contextmanager
def user_ai_session(config: UserAIConfig | None, *, required=False):
    if config is None:
        if required:
            raise UserAIError("AI_CONFIG_REQUIRED", "Supply your own ai_config for this operation.")
        yield None
        return
    # Official destinations only. Never read environment keys or base URLs.
    base_url = {
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com/v1",
    }[config.provider]
    try:
        client = OpenAI(
            api_key=config.api_key.get_secret_value(),
            base_url=base_url,
            timeout=30.0,
            max_retries=0,
        )
    except Exception:
        raise UserAIError("AI_CONFIG_INVALID", "Unable to initialise the user AI client.") from None
    runtime = UserAIRuntime(client, config.model)
    try:
        yield runtime
    finally:
        runtime.close()


class UserAIRoute(APIRoute):
    """Do not echo request bodies or provider payloads in API errors."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def safe_handler(request):
            try:
                return await original(request)
            except RequestValidationError as exc:
                # FastAPI normally includes raw input (possibly the entire key).
                errors = [{"loc": error["loc"], "type": error["type"]} for error in exc.errors()]
                raise HTTPException(
                    422, detail={"code": "INVALID_REQUEST", "errors": errors}
                ) from None
            except UserAIError as exc:
                status = {
                    "AI_CONFIG_REQUIRED": 422,
                    "AI_CONFIG_INVALID": 422,
                    "AI_AUTH_FAILED": 401,
                    "AI_ACCESS_DENIED": 403,
                    "AI_QUOTA_EXCEEDED": 429,
                    "AI_RATE_LIMITED": 429,
                    "AI_MODEL_UNAVAILABLE": 422,
                    "AI_TIMEOUT": 504,
                }.get(exc.code, 502)
                raise HTTPException(
                    status, detail={"code": exc.code, "message": str(exc)}
                ) from None

        return safe_handler
