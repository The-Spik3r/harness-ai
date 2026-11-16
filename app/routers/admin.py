import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.database import (
    count_action_decisions,
    count_audit_logs,
    list_action_decisions,
    list_audit_logs,
    summary_snapshot,
)
from app.db.models import ActionDecisionRow
from app.middleware.auth import require_identity, require_permission
from app.models.schemas import (
    ActionClassificationEntry,
    ActionDecisionEntry,
    ActionsResponse,
    AuditQueryEntry,
    AuditResponse,
    StatsResponse,
)
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
            # A verbatim passthrough (PRD-008 STORY-011). `list_audit_logs`
            # builds its rows through `_row_to_audit_log`, which has mapped
            # this column since STORY-008 -- the value was already in hand
            # here and merely went unprojected.
            session_id=log.session_id,
            timestamp=log.timestamp,
            model=log.model_used,
            prompt_hash=log.prompt_hash,
            was_duplicate_blocked=log.was_duplicate_blocked,
            suspicious_pattern_detected=log.suspicious_pattern is not None,
            # Verbatim passthrough (PRD-011 D6). `suspicious_pattern_detected`
            # is deliberately not narrowed to blocks; `pattern_action` says
            # which it was, NULL on rows written before PRD-011.
            pattern_role=log.pattern_role,
            pattern_action=log.pattern_action,
            # Verbatim passthrough (PRD-012 D9); NULL on pre-PRD-012 rows.
            profile=log.profile,
            # Verbatim passthrough (PRD-013 6.10). `_row_to_audit_log` has
            # mapped all eight since STORY-002: NULL for the six nullable ones
            # on pre-PRD-013 rows, and the two flags as bools. `dedup_key`
            # stays unprojected (PRD-009 D5).
            ingress=log.ingress,
            message_count=log.message_count,
            input_tokens=log.input_tokens,
            output_tokens=log.output_tokens,
            streamed=log.streamed,
            has_tool_calls=log.has_tool_calls,
            conversation_key=log.conversation_key,
            limit_exceeded=log.limit_exceeded,
            # Verbatim passthrough (PRD-015 Section 10); NULL off `/v1`.
            ignored_params=log.ignored_params,
            device=log.device,
            pii_detected_input=log.pii_detected_input,
            pii_detected_output=log.pii_detected_output,
            pii_entities=log.pii_entities.split(",") if log.pii_entities else [],
        )
        for log in list_audit_logs(limit=100, user_id=scope_user_id)
    ]
    return AuditResponse(total=total, queries=queries)


# PRD-016 Section 10: `?limit=` 1-500, default 100. 100 is `list_audit_logs`'
# and `list_action_decisions`' default.
ACTIONS_LIMIT_DEFAULT = 100
ACTIONS_LIMIT_MAX = 500

# PRD-016 Section 10: `?decision=allow|flag|deny`. This restates
# `ACTION_DECISION_VALUES` (app/db/models.py) because a `Literal` cannot be
# built from a runtime tuple; tests/test_admin_actions.py pins the two equal.
# FastAPI rejects any other value with 422 before the handler runs.
ActionDecisionFilter = Literal["allow", "flag", "deny"]


@router.get("/audit/actions", response_model=ActionsResponse)
def get_audit_actions(
    identity: Identity = Depends(require_identity),
    limit: int = Query(ACTIONS_LIMIT_DEFAULT, ge=1, le=ACTIONS_LIMIT_MAX),
    decision: Optional[ActionDecisionFilter] = Query(None),
) -> ActionsResponse:
    """The most recent action decisions, newest first (PRD-016 F11, 9.1).

    Scoped exactly as `GET /audit`: `audit:read:all` reads every user's rows,
    `audit:read:own` only the caller's, and neither is a 403 naming
    `audit:read:own`. The scoping is a row filter only, with no per-role
    masking, as on `GET /audit`.
    """
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

    entries = [
        _action_entry(row)
        for row in list_action_decisions(
            limit=limit, user_id=scope_user_id, decision=decision
        )
    ]
    return ActionsResponse(entries=entries)


def _action_entry(row: ActionDecisionRow) -> ActionDecisionEntry:
    # A verbatim field passthrough (PRD-016 Section 10), except
    # `classifications`: the column is JSON text, and decoding it is the
    # reader's job (`ActionDecisionRow`'s docstring). It is only ever written by
    # `action_audit._classifications_json`, so a decode failure is a corrupt
    # row and surfaces as a 500, as a broken `/stats` read does. No catch.
    return ActionDecisionEntry(
        id=row.id,
        timestamp=row.timestamp,
        audit_id=row.audit_id,
        user_id=row.user_id,
        role=row.role,
        tool_call_id=row.tool_call_id,
        tool_name=row.tool_name,
        operation_kind=row.operation_kind,
        target_preview=row.target_preview,
        decision=row.decision,
        rule=row.rule,
        reason=row.reason,
        granted_by=row.granted_by,
        classifications=[
            ActionClassificationEntry(**c) for c in json.loads(row.classifications)
        ],
        policy_digest=row.policy_digest,
    )


@router.get(
    "/stats",
    response_model=StatsResponse,
    dependencies=[Depends(require_permission(PERMISSION_STATS_READ))],
)
def get_stats() -> StatsResponse:
    # One statement for the twelve audit figures; PRD-016 adds a second, over
    # `action_decisions`, for three more (see below). The twelve were nine
    # sequential reads (PRD-007 Section 6 Pattern 3). Against a local file the fan-out cost
    # nothing; against a remote endpoint it was nine round trips per call, and
    # the latency scaled with the number of figures the response happens to
    # report. `summary_snapshot()` (STORY-010) reads them all in one. PRD-013
    # added three more (`input_tokens`, `output_tokens`,
    # `blocked_usage_limits`) to the same row.
    #
    # **`row_limit=0` is how this endpoint declines the one figure it does not
    # report.** The
    # batch returns `rows` -- the register's audit rows -- which `/stats` has no
    # field for. It cannot be projected away: `_SUMMARY_SQL` is a fixed
    # thirteen-column SELECT and per-figure projection would reopen STORY-010's
    # design. But the rows subquery ends in `LIMIT ?`, and that `?` is
    # `row_limit`, so 0 empties the column instead. Left at the default 100 this
    # would put up to 100 fully serialized audit rows -- nineteen fields each,
    # two of them preview strings -- on the wire per call with nothing reading
    # them, which is the transfer cost Section 6 Pattern 4 exists to avoid.
    # Verified against the endpoint: the column comes back `[]`, not NULL, and
    # the other figures are identical to the unlimited call.
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
    # PRD-016 F11. A second statement, against a different table, rather than
    # folded into `_SUMMARY_SQL`: `SUMMARY_FIGURES` is a pinned 13-tuple
    # (tests/test_audit_stats_prd013.py), and widening it would reopen
    # STORY-010's batched read for a table it never reads. `/stats` is
    # therefore two round trips, one per table; the "one `audit_logs` read"
    # claim still holds (tests/test_stats_router.py counts `audit_logs`
    # statements only).
    action_counts = count_action_decisions()

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
        # PRD-013 6.10. Three more figures from the same statement, so still
        # one round trip.
        input_tokens=snapshot.input_tokens,
        output_tokens=snapshot.output_tokens,
        blocked_usage_limits=snapshot.blocked_usage_limits,
        # PRD-016 F11 / Section 10: every key is present, 0 on an empty table.
        actions_denied=action_counts["deny"],
        actions_flagged=action_counts["flag"],
        actions_allowed=action_counts["allow"],
    )
