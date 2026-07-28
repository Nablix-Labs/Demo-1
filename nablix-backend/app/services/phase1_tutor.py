from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


_CONFIG_PATH: Path = Path(__file__).resolve().parents[2] / "configs" / "phase1_tutor.yaml"


class Phase1TutorMessages(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transition_to_orientation_message: str
    shared_video_transition_message: str
    before_video_message: str
    video_to_worked_example_message: str
    between_videos_message: str
    worked_example_to_guided_message: str


@lru_cache(maxsize=1)
def load_phase1_tutor_messages() -> Phase1TutorMessages:
    raw_config: object = yaml.safe_load(_CONFIG_PATH.read_text())
    return Phase1TutorMessages.model_validate(raw_config)
