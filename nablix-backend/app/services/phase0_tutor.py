from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


_CONFIG_PATH: Path = Path(__file__).resolve().parents[2] / "configs" / "phase0_tutor.yaml"


class Phase0TutorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intro_message: str
    neutral_transition_message: str
    gaps_transition_message: str
    no_gaps_transition_message: str


@lru_cache(maxsize=1)
def load_phase0_tutor_config() -> Phase0TutorConfig:
    raw_config: object = yaml.safe_load(_CONFIG_PATH.read_text())
    return Phase0TutorConfig.model_validate(raw_config)
