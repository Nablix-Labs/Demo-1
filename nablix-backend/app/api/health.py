from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import get_settings
from app.models.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """
    Health check endpoint to verify if the API is running.
    Returns the current server time and application name.
    """
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        app=settings.app_name,
        version=settings.app_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
        mode="inprocess",
    )
