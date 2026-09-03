"""Centralised configuration for ClaimTrace.

All settings are read from environment variables with sensible defaults.
Secrets (API keys) MUST come from the environment — never hardcoded.

Usage:
    from .config import settings
    client = OpenAI(api_key=settings.openai_api_key)
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    # ── LLM Provider ──────────────────────────────────────
    llm_provider: str = "openai"  # openai | gemini | anthropic | ollama

    # ── OpenAI ────────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # ── Google Gemini ─────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # ── Anthropic Claude ──────────────────────────────────
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # ── Ollama (local) ────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3.1"

    # ── Embedding ─────────────────────────────────────────
    embedding_model: str = "all-MiniLM-L6-v2"

    # ── Server ────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_reload: bool = True

    # ── CORS ──────────────────────────────────────────────
    cors_origins: list[str] = field(default_factory=lambda: [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "chrome-extension://*",
    ])

    # ── Upload ────────────────────────────────────────────
    max_upload_size_mb: int = 50
    upload_dir: Path = Path("uploads")
    papers_file: Path = Path("uploads/papers.json")
    parsed_dir: Path = Path("uploads/parsed")

    # ── Parser ───────────────────────────────────────────
    # Yi Jiang's PDF-to-Markdown converter uses Java locally by default.
    # Set PARSER_HYBRID to "docling-fast" or "hancom-ai" when the optional
    # local hybrid service is running on PARSER_HYBRID_URL.
    parser_hybrid: str = "off"
    parser_hybrid_mode: str | None = None
    parser_hybrid_url: str = "http://localhost:5002"
    parser_use_struct_tree: bool = False

    @property
    def is_llm_configured(self) -> bool:
        """Check whether any LLM provider has a valid API key set.

        Returns False in CI / local-dev-without-keys — the verifier
        will use local deterministic evidence matching.
        """
        key_checks = {
            "openai": self.openai_api_key,
            "gemini": self.gemini_api_key,
            "anthropic": self.anthropic_api_key,
            "ollama": True,  # ollama is always "configured" since it's local
        }
        return bool(key_checks.get(self.llm_provider, False))

    @property
    def llm_model_name(self) -> str:
        """Return the model name for the active provider."""
        model_map = {
            "openai": self.openai_model,
            "gemini": self.gemini_model,
            "anthropic": self.anthropic_model,
            "ollama": self.ollama_model,
        }
        return model_map.get(self.llm_provider, self.openai_model)


def _load_settings() -> Settings:
    """Load settings from environment variables.

    Reads .env file if present (via the caller's environment).
    """
    origins_raw = os.getenv("CORS_ORIGINS", "")
    origins = [o.strip() for o in origins_raw.split(",") if o.strip()] if origins_raw else [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "chrome-extension://*",
    ]

    upload_dir = Path(os.getenv("UPLOAD_DIR", "uploads"))
    papers_file = Path(os.getenv("PAPERS_FILE", str(upload_dir / "papers.json")))
    parsed_dir = Path(os.getenv("PARSED_DIR", str(upload_dir / "parsed")))

    return Settings(
        # LLM
        llm_provider=os.getenv("CLAIMTRACE_LLM_PROVIDER", "openai"),
        # OpenAI
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        # Gemini
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        # Anthropic
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
        # Ollama
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1"),
        # Embedding
        embedding_model=os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        # Server
        backend_host=os.getenv("BACKEND_HOST", "0.0.0.0"),
        backend_port=int(os.getenv("BACKEND_PORT", "8000")),
        backend_reload=os.getenv("BACKEND_RELOAD", "true").lower() == "true",
        # CORS
        cors_origins=origins,
        # Upload
        max_upload_size_mb=int(os.getenv("MAX_UPLOAD_SIZE_MB", "50")),
        upload_dir=upload_dir,
        papers_file=papers_file,
        parsed_dir=parsed_dir,
        parser_hybrid=os.getenv("PARSER_HYBRID", "off"),
        parser_hybrid_mode=os.getenv("PARSER_HYBRID_MODE") or None,
        parser_hybrid_url=os.getenv("PARSER_HYBRID_URL", "http://localhost:5002"),
        parser_use_struct_tree=os.getenv("PARSER_USE_STRUCT_TREE", "false").lower() == "true",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings singleton.

    Use this everywhere instead of reading os.getenv() directly:
        from backend.src.config import get_settings
        settings = get_settings()
        api_key = settings.openai_api_key
    """
    return _load_settings()


# Module-level convenience alias
settings = get_settings()
