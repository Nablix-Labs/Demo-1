from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.api.auth import AccessToken
from app.models.interaction import (
    DeferredCanvasTeachingPlanResponse,
    InteractionRequest,
    InteractionResponse,
    StaleTurnResponse,
)
from app.models.fields import SessionId, StudentId, TurnId
from app.services.interaction_service import process_interaction, recover_session_for_read
from app.services.session_service import deferred_canvas_teaching_plan_for

router = APIRouter()


@router.post(
    "/interaction",
    response_model=InteractionResponse,
    responses={409: {"model": StaleTurnResponse}},
)
async def interaction_endpoint(
    request: InteractionRequest,
    access_token: AccessToken,
) -> InteractionResponse | JSONResponse:
    if (
        request.input_source == "VOICE"
        and request.interaction_type == "ANSWER_SUBMISSION"
        and request.current_phase != "TEACH_BACK"
        and request.canvas_state is None
    ):
        raise HTTPException(
            status_code=422,
            detail="canvas_state is required for REST VOICE answer submissions.",
        )
    response = await process_interaction(request, access_token)
    if isinstance(response, StaleTurnResponse):
        return JSONResponse(status_code=409, content=response.model_dump())
    return response


@router.get(
    "/interaction/{session_id}/canvas-teaching-plan/{turn_id}",
    response_model=DeferredCanvasTeachingPlanResponse,
)
async def deferred_canvas_teaching_plan_endpoint(
    session_id: SessionId,
    turn_id: TurnId,
    student_id: StudentId,
    access_token: AccessToken,
) -> DeferredCanvasTeachingPlanResponse:
    await recover_session_for_read(session_id, student_id, access_token)
    plan = deferred_canvas_teaching_plan_for(session_id, turn_id)
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="No deferred canvas teaching plan exists for this turn.",
        )
    return plan
