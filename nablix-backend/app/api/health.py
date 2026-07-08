from datetime import datetime, timezone
from typing import Literal

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
    mode: Literal["mock", "live"] = "mock" if settings.use_mock_tutor else "live"
    return HealthResponse(
        status="healthy",
        app=settings.app_name,
        version=settings.app_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
        mode=mode,
    )
