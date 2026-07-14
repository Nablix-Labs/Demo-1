from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health response returned by the public health check."""

    status: Literal["healthy"]
    app: str
    version: str
    timestamp: str
    # The tutor always runs in-process; kept as a field so the payload shape is stable.
    mode: Literal["inprocess"]
