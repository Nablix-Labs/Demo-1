from typing import NoReturn

from fastapi import HTTPException

from app.models.hint import HintRequest


async def process_hint(request: HintRequest, access_token: str) -> NoReturn:
    """Reject obsolete manual hint requests."""

    del request, access_token
    raise HTTPException(
        status_code=410,
        detail="Manual hint requests were replaced by automatic Schema 3.0 support.",
    )
