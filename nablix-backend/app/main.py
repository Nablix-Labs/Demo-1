from datetime import UTC, datetime
import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import ai_engine, canvas, health, hint, interaction, session, voice
from app.core.config import get_settings
from app.middleware.request_logging import log_requests


app: FastAPI = FastAPI(
    title="Nablix AI Math Tutor API",
    version="1.0.0",
)
logger: logging.Logger = logging.getLogger(__name__)
settings = get_settings()

# Registering middleware for logging requests and responses
app.middleware("http")(log_requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registering API routes
app.include_router(health.router, tags=["Health"])
app.include_router(ai_engine.router, prefix="/ai-engine", tags=["AI Engine"])
app.include_router(session.router, prefix="/session", tags=["Session"])
app.include_router(interaction.router, tags=["Interaction"])
app.include_router(hint.router, prefix="/hint", tags=["Hints"])
app.include_router(canvas.router, prefix="/canvas", tags=["Canvas"])
app.include_router(voice.router, prefix="/voice", tags=["Voice"])


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _request_id(request: Request) -> str:
    header_request_id: str | None = request.headers.get("x-request-id")
    if header_request_id is not None and len(header_request_id.strip()) > 0:
        return header_request_id
    return f"REQ{uuid4().hex[:8].upper()}"


def _validation_field(error: dict[str, object]) -> str | None:
    location = error.get("loc")
    if not isinstance(location, list) and not isinstance(location, tuple):
        return None

    for item in reversed(location):
        if isinstance(item, str) and item != "body":
            return item
    return None


def _validation_message(error: dict[str, object]) -> str:
    message = error.get("msg")
    if not isinstance(message, str):
        return "Invalid request."
    return message


def _validation_error_code(error: dict[str, object], field: str | None) -> str:
    error_type: object = error.get("type")
    message: str = _validation_message(error)
    if error_type == "json_invalid":
        return "INVALID_JSON"
    if error_type == "missing":
        return "MISSING_FIELD"
    if field in ("student_id", "session_id"):
        return "INVALID_FORMAT"
    if "exceeds the maximum" in message:
        return "INPUT_TOO_LONG"
    return "INVALID_VALUE"


def _validation_response_message(
    error: dict[str, object],
    error_code: str,
    field: str | None,
) -> str:
    if error_code == "INVALID_JSON":
        return "Request body must be valid JSON."
    if error_code == "MISSING_FIELD" and field is not None:
        return f"{field} is required."
    if error_code == "INVALID_FORMAT" and field == "student_id":
        return "student_id must follow the format ST followed by three digits."
    if error_code == "INVALID_FORMAT" and field == "session_id":
        return "session_id must follow the format SESSION followed by three digits."
    if error_code == "INPUT_TOO_LONG":
        field_name: str = field if field is not None else "input"
        return f"{field_name} must be 500 characters or fewer."
    if field == "interaction_type":
        return (
            "interaction_type must be one of ANSWER_SUBMISSION, HINT_REQUEST, "
            "CANVAS_SUBMISSION, SESSION_START, SESSION_END."
        )
    if field == "current_phase":
        return (
            "current_phase must be one of DIAGNOSTIC, CONCEPT_ORIENTATION, "
            "GUIDED_PRACTICE, INDEPENDENT_PRACTICE, REVIEW."
        )
    return _validation_message(error)


# Adding the global exception handlers

def _error_response(
    request: Request,
    status_code: int,
    error_code: str,
    message: str,
    field: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": error_code,
            "message": message,
            "field": field,
            "timestamp": _utc_timestamp(),
            "request_id": _request_id(request),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors: list[dict[str, object]] = exc.errors()
    first_error: dict[str, object] = errors[0] if len(errors) > 0 else {}
    field: str | None = _validation_field(first_error)
    error_code: str = _validation_error_code(first_error, field)
    return _error_response(
        request,
        422,
        error_code,
        _validation_response_message(first_error, error_code, field),
        field,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error_response(request, exc.status_code, "HTTP_ERROR", str(exc.detail))


@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error")
    return _error_response(
        request, 500, "INTERNAL_ERROR", "Something went wrong. Please try again."
    )
