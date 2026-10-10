"""Explicit official endpoints and protocol adapters for user-owned AI requests."""

import re
from enum import Enum
from types import SimpleNamespace

import httpx


class AIProvider(str, Enum):
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    XAI = "xai"
    MISTRAL = "mistral"
    COHERE = "cohere"
    QWEN = "qwen"
    MOONSHOT = "moonshot"
    ZHIPU = "zhipu"
    MINIMAX = "minimax"
    DOUBAO = "doubao"
    GROQ = "groq"
    TOGETHER = "together"
    FIREWORKS = "fireworks"
    SILICONFLOW = "siliconflow"
    OPENROUTER = "openrouter"


# Regions are explicit, finite presets, never arbitrary destinations from a request.
ENDPOINTS = {
    "openai": {"global": "https://api.openai.com/v1"},
    "deepseek": {"global": "https://api.deepseek.com/v1"},
    "anthropic": {"global": "https://api.anthropic.com/v1"},
    "gemini": {"global": "https://generativelanguage.googleapis.com/v1beta/openai"},
    "xai": {"global": "https://api.x.ai/v1"},
    "mistral": {"global": "https://api.mistral.ai/v1"},
    "cohere": {"global": "https://api.cohere.ai/compatibility/v1"},
    "qwen": {
        "china": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "singapore": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "us": "https://dashscope-us.aliyuncs.com/compatible-mode/v1",
    },
    "moonshot": {"global": "https://api.moonshot.ai/v1", "china": "https://api.moonshot.cn/v1"},
    "zhipu": {"china": "https://open.bigmodel.cn/api/paas/v4"},
    "minimax": {"global": "https://api.minimax.io/v1", "china": "https://api.minimaxi.com/v1"},
    "doubao": {"china": "https://ark.cn-beijing.volces.com/api/v3"},
    "groq": {"global": "https://api.groq.com/openai/v1"},
    "together": {"global": "https://api.together.ai/v1"},
    "fireworks": {"global": "https://api.fireworks.ai/inference/v1"},
    "siliconflow": {
        "china": "https://api.siliconflow.cn/v1",
        "global": "https://api.siliconflow.com/v1",
    },
    "openrouter": {"global": "https://openrouter.ai/api/v1"},
}


def endpoint_for(provider, region=None, workspace=None):
    presets = ENDPOINTS[provider]
    selected = region or next(iter(presets))
    if selected not in presets:
        raise ValueError("Unsupported provider region.")
    if workspace:
        if provider != "qwen" or selected not in {"china", "singapore"}:
            raise ValueError("Workspace is only supported for Qwen China or Singapore.")
        location = "cn-beijing" if selected == "china" else "ap-southeast-1"
        return f"https://{workspace}.{location}.maas.aliyuncs.com/compatible-mode/v1"
    return presets[selected]


def prepare_completion(provider, model, kwargs):
    """Normalize only documented differences; never retry failed billable calls."""
    params = dict(kwargs)
    if "messages" in params:
        params["messages"] = [dict(message) for message in params["messages"]]
    # Reasoning models often reject a fixed temperature. Use their own default.
    if provider not in {"openai", "deepseek"} or model.startswith(("o1", "o3", "o4", "gpt-5")):
        params.pop("temperature", None)
    # MiniMax does not promise OpenAI JSON mode; keep local output validation.
    if provider == "minimax" and params.pop("response_format", None):
        params["messages"].append(
            {
                "role": "user",
                "content": "Return only the requested JSON object, without commentary.",
            }
        )
    # Qwen JSON mode requires thinking to be disabled on compatible hybrid models.
    if provider == "qwen" and model.startswith("qwen3"):
        params["extra_body"] = {**params.get("extra_body", {}), "enable_thinking": False}
    if provider == "openrouter":
        params["extra_body"] = {
            **params.get("extra_body", {}),
            "provider": {"require_parameters": True},
        }
    return params


def normalize_completion(provider, result):
    """Reject partial generations before downstream code can accept valid-looking JSON."""
    choices = getattr(result, "choices", None)
    if not choices:
        raise ValueError("The provider returned no completion.")
    choice = choices[0]
    finish = getattr(choice, "finish_reason", None)
    if finish is not None and finish != "stop":
        raise ValueError("The provider did not finish a text completion.")
    if provider == "minimax":
        content = choice.message.content
        if isinstance(content, str):
            # M2.x embeds reasoning before the answer. Do not alter JSON string values.
            content = re.sub(r"^\s*<think>.*?</think>\s*", "", content, flags=re.DOTALL)
            if content.lstrip().startswith("<think>"):
                raise ValueError("The provider returned incomplete reasoning.")
            choice.message.content = content
    return result


class AnthropicMessagesClient:
    """Minimal native text Messages adapter for the existing Engine client contract."""

    def __init__(self, *, api_key, base_url, timeout=30.0):
        self._http = httpx.Client(
            base_url=base_url + "/",
            timeout=timeout,
            follow_redirects=False,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )

    @property
    def chat(self):
        return SimpleNamespace(completions=self)

    def create(self, **kwargs):
        messages = kwargs["messages"]
        system = [m["content"] for m in messages if m["role"] in {"system", "developer"}]
        if kwargs.get("response_format"):
            system.append("Return only the requested JSON object, without markdown or commentary.")
        body = {
            "model": kwargs["model"],
            "max_tokens": 4096,
            "messages": [dict(m) for m in messages if m["role"] in {"user", "assistant"}],
        }
        if system:
            body["system"] = "\n\n".join(system)
        response = self._http.post("messages", json=body, timeout=kwargs.get("timeout", 30.0))
        response.raise_for_status()
        payload = response.json()
        if payload.get("stop_reason") != "end_turn":
            raise ValueError("The provider did not complete a text response.")
        content = "".join(
            block["text"] for block in payload.get("content", []) if block.get("type") == "text"
        )
        if not content:
            raise ValueError("The provider returned no text.")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    def close(self):
        self._http.close()
