"""Per-request capture of raw Student Model exchanges for development."""

from contextvars import ContextVar


_Capture = tuple[list[dict[str, object]], list[dict[str, object]]]
_capture: ContextVar[_Capture | None] = ContextVar(
    "student_model_debug_capture",
    default=None,
)


def begin(enabled: bool) -> None:
    """Start a fresh capture for one interaction when the dev flag is enabled."""

    _capture.set(([], []) if enabled else None)


def record_request(body: dict[str, object]) -> None:
    """Record one outbound Student Model request body, if enabled."""

    capture = _capture.get()
    if capture is not None:
        capture[0].append(body)


def record_response(body: dict[str, object]) -> None:
    """Record one raw Student Model response or error body, if enabled."""

    capture = _capture.get()
    if capture is not None:
        capture[1].append(body)


def payload() -> dict[str, object] | None:
    """Return paired request/response arrays, omitting empty disabled captures."""

    capture = _capture.get()
    if capture is None or (not capture[0] and not capture[1]):
        return None
    return {
        "student_model_request": capture[0],
        "student_model_response": capture[1],
    }
