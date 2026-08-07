"""ClaimTrace FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import audit, health, parse, verify

app = FastAPI(
    title="ClaimTrace API",
    description="Academic Citation Audit Engine",
    version="0.1.0",
)

# CORS: allow frontend dev server and extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "chrome-extension://*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(health.router, tags=["health"])
app.include_router(parse.router, prefix="/api", tags=["parse"])
app.include_router(verify.router, prefix="/api", tags=["verify"])
app.include_router(audit.router, prefix="/api", tags=["audit"])


@app.on_event("startup")
async def startup():
    """Initialize services on startup."""
    # Create upload directory if needed
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
