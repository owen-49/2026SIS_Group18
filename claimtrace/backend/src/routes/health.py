"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Return service health status."""
    return {
        "status": "ok",
        "service": "claimtrace-api",
        "version": "0.1.0",
    }
