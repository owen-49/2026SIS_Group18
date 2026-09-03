"""ClaimTrace FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routes import audit, bib, health, papers, parse, verify

# ── Load configuration ─────────────────────────────────────
settings = get_settings()

app = FastAPI(
    title="ClaimTrace API",
    description="Academic Citation Audit Engine",
    version="0.1.0",
)

# CORS: allow frontend dev server and extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in settings.cors_origins if "*" not in origin],
    allow_origin_regex=r"^chrome-extension://[a-z]{32}$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(health.router, tags=["health"])
app.include_router(parse.router, prefix="/api", tags=["parse"])
app.include_router(papers.router, prefix="/api", tags=["papers"])
app.include_router(verify.router, prefix="/api", tags=["verify"])
app.include_router(audit.router, prefix="/api", tags=["audit"])
app.include_router(bib.router, prefix="/api", tags=["bib"])


@app.on_event("startup")
async def startup():
    """Initialize services on startup."""
    # Create upload directory
    settings.upload_dir.mkdir(exist_ok=True)

    # Store settings in app.state so routes can access them
    app.state.settings = settings

    # Build LLM client from configured provider
    from engine.llm_client import build_llm_client

    provider = settings.llm_provider
    provider_configs = {
        "openai": {
            "api_key": settings.openai_api_key,
            "base_url": settings.openai_base_url,
        },
        "gemini": {
            "api_key": settings.gemini_api_key,
            "base_url": None,
        },
        "anthropic": {
            "api_key": settings.anthropic_api_key,
            "base_url": None,
        },
        "ollama": {
            "api_key": "",
            "base_url": settings.ollama_base_url,
        },
    }

    config = provider_configs.get(provider, {})
    app.state.llm_client = build_llm_client(provider=provider, **config)
    app.state.llm_model = settings.llm_model_name

    if app.state.llm_client:
        print(f"[ClaimTrace] LLM ready: {provider}/{settings.llm_model_name}")
    else:
        print(f"[ClaimTrace] LLM NOT configured ({provider}). "
              f"Set API key in .env. Audit will use local evidence matching.")
