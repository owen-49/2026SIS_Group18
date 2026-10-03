"""Health check endpoint."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.runtime_checks import runtime_checks

router = APIRouter()


@router.get("/health")
async def health_check():
    """Return service health status."""
    return {
        "status": "ok",
        "service": "claimtrace-api",
        "version": "0.1.0",
    }


@router.get("/ready")
def readiness_check():
    """Report local runtime readiness, independent of paid AI credentials."""
    checks = runtime_checks()
    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )
