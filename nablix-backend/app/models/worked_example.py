from pydantic import BaseModel


class WorkedExampleStep(BaseModel):
    step_id: str
    sequence_no: int
    screen_content: str | None
    narration_text: str | None
    must_show: str | None
    must_not_show: str | None


class WorkedExample(BaseModel):
    worked_example_id: str
    title: str
    covered_micro_skill_ids: list[str]
    final_answer: str | None
    student_answer_required: bool
    steps: list[WorkedExampleStep]


