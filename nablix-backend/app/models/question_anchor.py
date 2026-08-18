from pydantic import BaseModel, Field


class QuestionTextAnchor(BaseModel):
    """One token of the served question text, addressable by the frontend.

    `char_start`/`char_end` index into the exact `current_question` string the
    same response carries, so the frontend resolves the position itself. The
    backend never sends coordinates for the question: it does not lay it out.
    """

    token_id: str
    text: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    label: str | None = None
