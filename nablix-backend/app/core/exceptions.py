from fastapi import Request, HTTPException
from app.core.logger import logger

#for unprocessable content, we are creating a custom exception class.
class ValidationException(HTTPException):
    def __init__(self, message: str, field: str):
        super().__init__(status_code = 422)
        self.message = message
        self.field = field

#for not found content, using 404 not found error.
class SessionNotFoundError(HTTPException):
    def __init__(self, session_id: str):
        super().__init__(status_code=404)
        self.message = f"Session with ID {session_id} not found."
        self.field = "session_id"

#for internal server errors, using 503 error. Not commonly used.
class AdapterError(HTTPException):
    def __init__(self,adapter_name:str, detail:str):
        super().__init__(status_code=503)
        self.message = "Service Temporarily Unavailable"
        self.field = None
        logger.error(
            "adapter_error",
            extra={
                "adapter_name": adapter_name,
                "detail": detail,
            },
        )
