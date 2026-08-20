from fastapi import APIRouter, Response

from app.adapters.provider import get_adapters
from app.api.auth import AccessToken
from app.core.exceptions import AdapterRequestRejected, WorkArtifactNotFoundError

router = APIRouter()


@router.get("/work-artifacts/{artifact_id}/pdf")
async def get_work_artifact_pdf(artifact_id: str, access_token: AccessToken) -> Response:
    """Proxy Student Model's stored PDF so the browser can reach it.

    An iframe pointed straight at Student Model's URL cannot carry a bearer
    token, and Student Model requires one to enforce per-student ownership on
    this read -- so this route exists purely to forward the caller's own
    token, never a service token.
    """

    try:
        content, content_type = await get_adapters().student_model.fetch_work_artifact_pdf(
            artifact_id, access_token
        )
    except AdapterRequestRejected as error:
        if error.status_code == 404:
            # Student Model's own 404 detail names its internal URL and raw
            # response body -- this route is browser-reachable, so that must
            # not leak here. Every other rejected status keeps the existing
            # DOWNSTREAM_FAILURE behavior (re-raised as-is).
            raise WorkArtifactNotFoundError(artifact_id) from None
        raise
    return Response(content=content, media_type=content_type)
