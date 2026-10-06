"""Browser-facing profile proxy; identity and persistence belong to Student Model."""

from fastapi import APIRouter, HTTPException

from app.adapters.provider import get_adapters
from app.api.auth import AccessToken
from app.core.exceptions import AdapterRequestRejected
from app.models.student_profile import StudentProfile, StudentProfilePatch

router = APIRouter(prefix="/students/me", tags=["Student Profile"])


def profile_rejection(error: AdapterRequestRejected) -> HTTPException:
    """Keep downstream status while withholding internal URLs and profile data."""
    messages: dict[int, str] = {
        401: "Your login has expired. Please sign in again.",
        403: "You do not have permission to access this profile.",
        404: "Profile service is not available. Please contact support.",
        422: "The profile service rejected these changes. Check the supplied values.",
    }
    return HTTPException(
        status_code=error.status_code,
        detail=messages.get(error.status_code, "The profile service rejected this request."),
    )


@router.get("/profile", response_model=StudentProfile)
async def get_student_profile(access_token: AccessToken) -> StudentProfile:
    try:
        return await get_adapters().student_model.fetch_student_profile(access_token)
    except AdapterRequestRejected as error:
        raise profile_rejection(error) from error


@router.patch("/profile", response_model=StudentProfile)
async def patch_student_profile(changes: StudentProfilePatch, access_token: AccessToken) -> StudentProfile:
    try:
        return await get_adapters().student_model.update_student_profile(changes, access_token)
    except AdapterRequestRejected as error:
        raise profile_rejection(error) from error
