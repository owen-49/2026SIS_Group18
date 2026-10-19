"""Discover and test user connections without persisting credentials or provider bodies."""

import json
import re
from time import perf_counter

import httpx
from fastapi import APIRouter

from ..services.ai_providers import ModelIncompatibleError
from ..services.user_ai_runtime import UserAIError, safe_provider_error
from ..user_ai import UserAIConfig, UserAIConnectionConfig, UserAIRoute, user_ai_session

router = APIRouter(route_class=UserAIRoute)
_NON_CHAT = re.compile(
    r"embedding|embed[-_]|tts|whisper|dall-e|moderation|image|audio|rerank|transcri|"
    r"stable-diffusion|flux|sora|video",
    re.I,
)


@router.post("/ai/models")
def list_models(config: UserAIConnectionConfig):
    with user_ai_session(config, required=True) as runtime:
        try:
            client = runtime.raw_client
            if config.provider == "anthropic":
                models = client.list_models()
            else:
                # Read just the first page, never follow provider supplied pagination URLs.
                models = client.models.list().data
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if isinstance(exc, httpx.HTTPStatusError):
                status = exc.response.status_code
            if status in {404, 405} or isinstance(exc, NotImplementedError):
                return {"supported": False, "models": []}
            raise safe_provider_error(exc) from None
        if not isinstance(models, list):
            raise UserAIError("AI_PROVIDER_FAILED", "The provider returned an invalid model list.")
        ids = set()
        secret = config.api_key.get_secret_value()
        for item in models:
            model_id = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
            if (
                isinstance(model_id, str)
                and 0 < len(model_id) <= 200
                and model_id == model_id.strip()
                and not any(ord(char) < 32 for char in model_id)
                and secret not in model_id
                and not _NON_CHAT.search(model_id)
            ):
                ids.add(model_id)
        return {"supported": True, "models": [{"id": value} for value in sorted(ids)[:500]]}


def incompatible_model_error():
    return UserAIError(
        "AI_MODEL_INCOMPATIBLE",
        "This model does not support the JSON output ClaimTrace needs. "
        "Choose another text chat model.",
    )


@router.post("/ai/test")
def test_connection(config: UserAIConfig):
    started = perf_counter()
    with user_ai_session(config, required=True) as runtime:
        try:
            result = runtime.create(
                messages=[
                    {"role": "user", "content": 'Return exactly this JSON object: {"ok": true}'}
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
        except UserAIError:
            # Keep existing Verify/Audit failure contracts while giving connection
            # checks a more specific diagnosis of rejected completion output.
            if runtime.incompatible_completion:
                raise incompatible_model_error() from None
            raise
        try:
            choice = result.choices[0]
            if choice.finish_reason != "stop":
                raise ModelIncompatibleError()
            payload = json.loads(choice.message.content)
            if not isinstance(payload, dict) or payload.get("ok") is not True:
                raise ModelIncompatibleError()
        except (ValueError, TypeError, AttributeError, IndexError):
            raise incompatible_model_error() from None
    # A caller can accidentally paste a key into the model field. Never echo it.
    model = config.model if config.api_key.get_secret_value() not in config.model else "[redacted]"
    return {"ok": True, "model": model, "latency_ms": round((perf_counter() - started) * 1000)}
