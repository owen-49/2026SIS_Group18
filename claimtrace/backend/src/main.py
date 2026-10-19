"""ClaimTrace FastAPI application entry point."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routes import ai, audit, bib, health, papers, parse, verify, verify_sources

# ── Logging ─────────────────────────────────────────────────
# No logger configuration would leave the root logger on Python's fallback
# handler, which only emits WARNING and above.  Parse progress logs (scan
# escalation, per-paper timings) are INFO, so configure them explicitly.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

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
app.include_router(ai.router, prefix="/api", tags=["ai"])
app.include_router(health.router, tags=["health"])
app.include_router(parse.router, prefix="/api", tags=["parse"])
app.include_router(papers.router, prefix="/api", tags=["papers"])
app.include_router(verify.router, prefix="/api", tags=["verify"])
app.include_router(verify_sources.router, prefix="/api", tags=["verify"])
app.include_router(audit.router, prefix="/api", tags=["audit"])
app.include_router(bib.router, prefix="/api", tags=["bib"])


@app.on_event("startup")
async def startup():
    """Initialize services on startup."""
    # Create upload directory
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    # Store settings in app.state so routes can access them
    app.state.settings = settings

    from .services.provider_chain_lookup import ProviderChainLookup, default_providers

    app.state.bibliography_lookup = ProviderChainLookup(
        default_providers(),
        timeout_seconds=settings.metadata_lookup_timeout_seconds,
    )
    # Finish or roll back file cleanup interrupted by an earlier deletion.
    from .services.paper_deletion_service import recover_pending_deletions

    pending_deletions = recover_pending_deletions()
    if pending_deletions:
        print(
            f"[ClaimTrace] {pending_deletions} pending paper deletion(s) "
            "could not be recovered."
        )

    from .services.pipeline_service import recover_interrupted_parses

    interrupted = recover_interrupted_parses()
    if interrupted:
        logging.getLogger(__name__).warning("Recovered %d interrupted PDF parses", interrupted)

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
        "deepseek": {
            "api_key": settings.deepseek_api_key,
            "base_url": settings.deepseek_base_url,
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
        print(
            f"[ClaimTrace] LLM NOT configured ({provider}). "
            "Set API key in .env. Single Verify uses a lexical baseline; "
            "reference metadata keeps its Parser/raw-text fallback, and "
            "Bibliography Audit still uses the OpenAlex/Crossref metadata chain."
        )


@app.on_event("shutdown")
def shutdown():
    """Stop accepting background parse work."""
    from .services.pipeline_service import shutdown_parse_queue

    shutdown_parse_queue()
