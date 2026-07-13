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

#for failed next-question fetches on a phase transition (Chirudeva 6.7).
class QuestionFetchError(HTTPException):
    def __init__(self, concept_id: str, phase: str):
        super().__init__(
            status_code=503,
            detail="Could not load the next question. Please try again.",
        )
        self.error_code = "QUESTION_FETCH_FAILED"
        logger.error(f"question_fetch_failed concept={concept_id} phase={phase}")


#for internal server errors, using 503 error. Not commonly used.
class AdapterError(HTTPException):
    def __init__(self,adapter_name:str, detail:str):
        super().__init__(status_code=503)
        self.message = "Service Temporarily Unavailable"
        self.field = None
        # Detail must be in the message itself: `extra` fields are not
        # rendered by the console formatter, which made failures invisible.
        logger.error(f"adapter_error adapter={adapter_name} detail={detail}")
