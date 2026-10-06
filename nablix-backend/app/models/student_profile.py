"""Student-owned profile contract shared with the Student Model handoff.

PATCH omits untouched fields, permits null only to clear grade_band, and never
accepts identity, guardian, account-status, avatar or consent writes.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, StringConstraints, model_validator

AgeBand = Literal["11–14 (KS3)", "14–16 (KS4)"]
GradeBand = Literal["Year 7", "Year 8", "Year 9", "Year 10", "Year 11"]
PreferredMode = Literal["voice", "text", "balanced"]
InputMode = Literal["voice", "text"]
PanelSide = Literal["left", "right"]
DisplayName = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=100)]
AccountStatus = Literal["registration_started", "consent_pending", "active", "consent_withdrawn", "suspended", "locked", "deleted"]


class ProfilePreferences(BaseModel):
    input_mode: InputMode | None
    panel_side: PanelSide | None


class ProfileGuardian(BaseModel):
    guardian_id: str
    name: str | None
    relationship: str | None
    email: str | None
    phone: str | None
    verified: StrictBool | None


class ProfileConsent(BaseModel):
    purpose: str
    accepted_at: str | None
    withdrawn_at: str | None


class StudentProfile(BaseModel):
    student_id: str = Field(min_length=1)
    student_code: str | None
    email: str | None
    tier: str | None
    account_status: AccountStatus
    display_name: str | None
    age_band: AgeBand | None
    grade_band: GradeBand | None
    preferred_mode: PreferredMode | None
    preferences: ProfilePreferences
    guardians: list[ProfileGuardian]
    avatar_url: HttpUrl | None = None
    consents: list[ProfileConsent] | None = None


class ProfilePreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_mode: InputMode | None = None
    panel_side: PanelSide | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> "ProfilePreferencesPatch":
        changes = self.model_dump(exclude_unset=True)
        if not changes or any(value is None for value in changes.values()):
            raise ValueError("Supply at least one non-null learning preference.")
        return self


class StudentProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: DisplayName | None = None
    age_band: AgeBand | None = None
    grade_band: GradeBand | None = None
    preferred_mode: PreferredMode | None = None
    preferences: ProfilePreferencesPatch | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> "StudentProfilePatch":
        changes = self.model_dump(exclude_unset=True)
        if not changes:
            raise ValueError("Supply at least one editable profile field.")
        if any(value is None for key, value in changes.items() if key != "grade_band"):
            raise ValueError("Only grade_band may be cleared with null.")
        return self
