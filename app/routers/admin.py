from fastapi import APIRouter, Depends, HTTPException

from app.db.database import (
    count_audit_logs,
    list_audit_logs,
    summary_snapshot,
)
from app.middleware.auth import require_identity, require_permission
from app.models.schemas import AuditQueryEntry, AuditResponse, StatsResponse
from app.services.authz import (
    PERMISSION_AUDIT_READ_ALL,
    PERMISSION_AUDIT_READ_OWN,
    PERMISSION_STATS_READ,
    PermissionDenied,
    authorize,
)
from app.services.identity import Identity

router = APIRouter()


@router.get("/audit", response_model=AuditResponse)
def get_audit(identity: Identity = Depends(require_identity)) -> AuditResponse:
    try:
        authorize(identity, PERMISSION_AUDIT_READ_ALL)
        scope_user_id = None
    except PermissionDenied:
        try:
            authorize(identity, PERMISSION_AUDIT_READ_OWN)
        except PermissionDenied as exc:
            raise HTTPException(
                status_code=403, detail=f"Permission denied: {exc.permission}"
            ) from exc
        scope_user_id = identity.user_id

    total = count_audit_logs(user_id=scope_user_id)
    queries = [
        AuditQueryEntry(
            audit_id=log.id,
            user_id=log.user_id,
            role=log.role,
            denied_permission=log.denied_permission,
            timestamp=log.timestamp,
            model=log.model_used,
            prompt_hash=log.prompt_hash,
            was_duplicate_blocked=log.was_duplicate_blocked,
            suspicious_pattern_detected=log.suspicious_pattern is not None,
            device=log.device,
            pii_detected_input=log.pii_detected_input,
            pii_detected_output=log.pii_detected_output,
            pii_entities=log.pii_entities.split(",") if log.pii_entities else [],
        )
        for log in list_audit_logs(limit=100, user_id=scope_user_id)
    ]
    return AuditResponse(total=total, queries=queries)


@router.get(
    "/stats",
    response_model=StatsResponse,
    dependencies=[Depends(require_permission(PERMISSION_STATS_READ))],
)
def get_stats() -> StatsResponse:
    # One statement, nine figures, where there were nine sequential reads
    # (PRD-007 Section 6 Pattern 3). Against a local file the fan-out cost
    # nothing; against a remote endpoint it was nine round trips per call, and
    # the latency scaled with the number of figures the response happens to
    # report. `summary_snapshot()` (STORY-010) reads them all in one.
    #
    # **`row_limit=0` is how this endpoint declines the tenth figure.** The
    # batch returns `rows` -- the register's audit rows -- which `/stats` has no
    # field for. It cannot be projected away: `_SUMMARY_SQL` is a fixed
    # ten-column SELECT and per-figure projection would reopen STORY-010's
    # design. But the rows subquery ends in `LIMIT ?`, and that `?` is
    # `row_limit`, so 0 empties the column instead. Left at the default 100 this
    # would put up to 100 fully serialized audit rows -- nineteen fields each,
    # two of them preview strings -- on the wire per call with nothing reading
    # them, which is the transfer cost Section 6 Pattern 4 exists to avoid.
    # Verified against the endpoint: the column comes back `[]`, not NULL, and
    # the other nine figures are identical to the unlimited call.
    #
    # `ranked_limit` is deliberately *not* passed. The three `top_*` figures
    # were read here through the functions' own default of 5, which is also
    # `summary_snapshot()`'s default -- so leaving it unpassed keeps the two
    # defaults tracking each other exactly as they did before.
    #
    # No error handling is added, because none is replaced. `SummarySnapshot`'s
    # named properties re-raise the failure recorded against a figure, so a
    # broken read still raises out of this function and still becomes a 500.
    # The `errors` partition is for the caller that wants per-figure
    # attribution -- the admin console (STORY-012) -- not for this one.
    #
    # Stays a plain `def`: FastAPI dispatches it to a threadpool, and
    # `summary_snapshot()` blocks. As `async def` that blocking call would sit
    # on the event loop, which is worse than the nine reads it replaces.
    snapshot = summary_snapshot(row_limit=0)

    total = snapshot.total_recorded
    successful = snapshot.successful_queries
    success_rate = f"{(successful / total * 100):.1f}%" if total > 0 else "0.0%"

    return StatsResponse(
        total_queries=total,
        blocked_duplicates=snapshot.blocked_duplicates,
        blocked_suspicious=snapshot.blocked_suspicious,
        unique_users=snapshot.unique_users,
        success_rate=success_rate,
        top_models=snapshot.top_models,
        top_users=snapshot.top_users,
        pii_detected_queries=snapshot.pii_detected_queries,
        top_pii_entities=snapshot.top_pii_entities,
    )
