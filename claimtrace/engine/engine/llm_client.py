"""LLM client factory.

Creates the right client for whatever provider is configured.
Hides provider-specific setup from the rest of the codebase.

Usage:
    from engine.llm_client import build_llm_client
    client = build_llm_client(provider="openai", api_key="sk-...", model="gpt-4o-mini")
    response = client.chat.completions.create(model=model, messages=[...])
"""

from typing import Any


def build_llm_client(
    provider: str = "openai",
    api_key: str = "",
    base_url: str | None = None,
    model: str = "gpt-4o-mini",
) -> Any | None:
    """Build an OpenAI-compatible client for the configured provider.

    All supported providers speak the OpenAI chat completions protocol,
    so we always return an OpenAI client — just pointed at different base URLs.

    Args:
        provider: "openai" | "deepseek" | "gemini" | "anthropic" | "ollama"
        api_key: API key for the provider.
        base_url: Override base URL (used by ollama and proxies).
        model: Not used in client construction, logged for debugging.

    Returns:
        An openai.OpenAI-compatible client, or None if misconfigured.
    """
    if provider == "ollama":
        from openai import OpenAI

        return OpenAI(
            base_url=base_url or "http://localhost:11434/v1",
            api_key="ollama",  # ollama doesn't check this, but the client requires it
        )

    if provider == "openai":
        if not api_key:
            return None
        from openai import OpenAI

        return OpenAI(
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
        )

    if provider == "deepseek":
        if not api_key:
            return None
        from openai import OpenAI

        return OpenAI(
            api_key=api_key,
            base_url=base_url or "https://api.deepseek.com/v1",
        )

    if provider == "gemini":
        if not api_key:
            return None
        from openai import OpenAI

        return OpenAI(
            api_key=api_key,
            base_url=base_url or "https://generativelanguage.googleapis.com/v1beta/openai/",
        )

    if provider == "anthropic":
        if not api_key:
            return None
        from openai import OpenAI

        return OpenAI(
            api_key=api_key,
            base_url=base_url or "https://api.anthropic.com/v1",
        )

    # Unknown provider — return None, caller falls back to mock mode
    return None


def build_llm_client_from_env() -> Any | None:
    """Build an LLM client from environment variables.

    Uses the same env vars as backend/src/config.py.

    Returns:
        OpenAI-compatible client, or None if not configured.
    """
    import os

    provider = os.getenv("CLAIMTRACE_LLM_PROVIDER", "openai")

    provider_configs = {
        "openai": {
            "api_key": os.getenv("OPENAI_API_KEY", ""),
            "base_url": os.getenv("OPENAI_BASE_URL", None),
        },
        "deepseek": {
            "api_key": os.getenv("OPENAI_API_KEY", ""),
            "base_url": os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
        },
        "gemini": {
            "api_key": os.getenv("GEMINI_API_KEY", ""),
            "base_url": None,
        },
        "anthropic": {
            "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
            "base_url": None,
        },
        "ollama": {
            "api_key": "",
            "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        },
    }

    config = provider_configs.get(provider, {})
    return build_llm_client(provider=provider, **config)
