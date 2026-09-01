from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth import require_permission
from app.models.schemas import QueryRequest, QueryResponse
from app.services.authz import PERMISSION_QUERY_SUBMIT
from app.services.duplicate_checker import DuplicateCheckError
from app.services.identity import Identity
from app.services.openrouter_client import OpenRouterError, call_openrouter
from app.services.pii_redactor import PiiRedactorError
from app.services.query_pipeline import run_query

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    identity: Identity = Depends(require_permission(PERMISSION_QUERY_SUBMIT)),
) -> QueryResponse:
    if request.user_id is not None and request.user_id != identity.user_id:
        raise HTTPException(
            status_code=403,
            detail="user_id does not match the authenticated identity",
        )

    try:
        return run_query(
            identity=identity,
            prompt=request.prompt,
            device=request.device,
            model=request.model,
            openrouter_api_key=request.openrouter_api_key,
            call_openrouter=call_openrouter,
        )
    except DuplicateCheckError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except PiiRedactorError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except OpenRouterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
