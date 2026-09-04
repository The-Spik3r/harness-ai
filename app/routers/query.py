from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth import require_permission
from app.models.schemas import QueryRequest, QueryResponse
from app.services import chat_sessions
from app.services.audit_logger import log_query
from app.services.authz import PERMISSION_QUERY_SUBMIT
from app.services.chat_sessions import ChatSessionError
from app.services.duplicate_checker import DuplicateCheckError
from app.services.identity import Identity
from app.services.openrouter_client import OpenRouterError, call_openrouter
from app.services.pii_redactor import PiiRedactorError
from app.services.query_pipeline import run_query

_FOREIGN_SESSION_DETAIL = "session_id does not belong to the authenticated identity"

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
        # A session id the caller does not own is refused here, beside the
        # user_id check above, because this is the boundary where an id from
        # outside the process first arrives (PRD-008 Section 9; Risk 3 --
        # `active_session_id` is a client-visible Reflex var and therefore
        # untrusted input). Four decisions worth stating, because each reads as
        # a mistake otherwise:
        #
        # 1. The `is not None` guard comes first, so `owns()` issues no query
        #    for the requests that omit the field -- which is most of them, and
        #    which must stay identical to the previous release.
        # 2. **This refusal is audited and the user_id mismatch above is not.**
        #    STORY-010 requires a rejected send to be "logged with the same
        #    rigour as an accepted one, which is PRD-001's founding property".
        #    The arm above predates that and is pinned by
        #    `tests/test_query_router.py` to write no row; this story adds a
        #    check, it does not revisit that one. Do not "fix" the asymmetry by
        #    making them match -- an existing test says which way it goes.
        # 3. `success=False` with the reason in `error_message`, and
        #    `denied_permission` left None. `_deny` in the pipeline logs a
        #    policy refusal as `success=True` because the row already names the
        #    permission that was denied. Here nothing was denied -- RBAC passed
        #    and `require_permission` admitted the request -- so a permission
        #    would be a lie, and `success=True` with no permission would make
        #    the row indistinguishable from an ordinary send. `audit_logs` has
        #    no column for "refused for a foreign session" and this story adds
        #    none.
        # 4. The supplied `session_id` goes on the row: it is what was
        #    attempted, and recording the attempt is the whole evidentiary value
        #    of the audited refusal. That it may name a row the caller does not
        #    own is expected -- `audit_logs` is append-only and Section 9
        #    already accepts orphaned session ids on it.
        #
        # Inside the `try` so a storage failure during the check maps to the
        # same 500 as one during the pipeline, through the chain below rather
        # than a second error-mapping site. `HTTPException` is caught by no arm
        # of that chain, so the 403 reaches the client unchanged.
        if request.session_id is not None and not chat_sessions.owns(
            identity, request.session_id
        ):
            log_query(
                user_id=identity.user_id,
                prompt=request.prompt,
                device=request.device,
                success=False,
                error_message=_FOREIGN_SESSION_DETAIL,
                role=identity.role,
                session_id=request.session_id,
            )
            raise HTTPException(status_code=403, detail=_FOREIGN_SESSION_DETAIL)

        return run_query(
            identity=identity,
            prompt=request.prompt,
            device=request.device,
            model=request.model,
            openrouter_api_key=request.openrouter_api_key,
            call_openrouter=call_openrouter,
            session_id=request.session_id,
        )
    except ChatSessionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except DuplicateCheckError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except PiiRedactorError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except OpenRouterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
