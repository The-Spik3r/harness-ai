import dataclasses
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from app.db import audit_journal
from app.db.database import insert_audit_log
from app.db.errors import StorageUnavailableError
from app.db.models import ActionDecisionRow, AuditLog
from app.services.duplicate_checker import hash_prompt

logger = logging.getLogger(__name__)

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_PREVIEW_LENGTH = 500


@dataclasses.dataclass(frozen=True)
class AuditRef:
    """Where an audit row is recorded (PRD-018 F7, D13, D14).

    `audit_id` is the committed row's id, or None when the row is only fsynced
    to the journal (released with `audit_id: null`, O2). `write_id` is always
    set: the row's key and the client-facing `audit_ref`.
    """

    audit_id: Optional[int]
    write_id: str


def _new_write_id() -> str:
    """A fresh idempotency key: `uuid.uuid4().hex`, 32 lowercase hex characters.

    The PRD-wide `write_id` convention (PRD-018 D4, STORY-004); STORY-008/009/010
    reuse this one helper rather than minting their own. Hex rather than
    `str(uuid4())` because the key appears verbatim in client-facing strings
    (`audit_ref`, `X-Harness-Audit-Ref`, `chatcmpl-harness-ref-<write_id>`) and a
    `"<batch>:<index>"` decision key reads unambiguously with no hyphen inside
    the batch part.
    """
    return uuid.uuid4().hex


def log_query(
    user_id: str,
    prompt: str,
    device: Optional[str] = None,
    response: Optional[str] = None,
    model_used: Optional[str] = None,
    tokens_used: Optional[int] = None,
    was_duplicate_blocked: bool = False,
    suspicious_pattern: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    pii_detected_input: bool = False,
    pii_detected_output: bool = False,
    pii_entities: Optional[list[str]] = None,
    role: Optional[str] = None,
    denied_permission: Optional[str] = None,
    session_id: Optional[str] = None,
    dedup_key: Optional[str] = None,
    # PRD-011 STORY-009. Defaulted, unlike _deny's session_id/dedup_key: only
    # the pattern block and flag arms have a hit to describe, and NULL is the
    # truth for every other row.
    pattern_role: Optional[str] = None,
    pattern_action: Optional[str] = None,
    # PRD-012 STORY-011 (D9). Defaulted here but never omitted in the
    # pipeline: every row run_conversation writes passes it explicitly --
    # _deny requires it, and tests/test_query_pipeline_pii_profiles.py scans
    # every direct call site -- because a forgotten arm must not write a NULL
    # that makes a `code` row's pii_detected_output = 0 read as "clean"
    # (the PRD-008 STORY-009 / PRD-009 Risk 6 rule). The default exists for
    # one caller: /query's foreign-session refusal (app/routers/query.py),
    # which writes before run_query resolves any profile, so NULL is the truth.
    profile: Optional[str] = None,
    # PRD-013 STORY-005 (Sections 6.2, 6.9). Defaulted here but never omitted
    # in the pipeline: every row run_conversation writes passes ingress,
    # message_count, conversation_key and streamed explicitly -- _deny
    # requires them, and tests/test_query_pipeline_audit_fields.py scans every
    # direct call site -- because a forgotten arm must be a TypeError or a red
    # test, not a NULL. ingress stays None for the direct callers (the test
    # suite, scripts/), where NULL is the honest record (6.9). The token pair
    # is set only by the two arms holding an upstream result. has_tool_calls
    # and limit_exceeded are accepted now and first set by PRD-016 and
    # STORY-011.
    ingress: Optional[str] = None,
    message_count: Optional[int] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    streamed: bool = False,
    has_tool_calls: bool = False,
    conversation_key: Optional[str] = None,
    limit_exceeded: Optional[str] = None,
    # PRD-015 STORY-007 (Section 7.3, D3). Defaulted here but never omitted in
    # the pipeline: every row run_conversation writes passes it explicitly --
    # _deny requires it, and tests/test_query_pipeline_audit_fields.py and
    # tests/test_query_pipeline_pii_profiles.py scan every direct call site --
    # because a forgotten arm must not write a `/v1` row that claims the client
    # got everything it asked for. The default exists for the callers that
    # never ignore anything: /query's foreign-session refusal
    # (app/routers/query.py), the test suite and scripts/, where NULL is the
    # truth. Stored verbatim: v1_translate builds the string, not this module.
    ignored_params: Optional[str] = None,
    # PRD-020 STORY-006 (D13). Defaulted because no caller passes them until
    # STORY-007, which passes them explicitly on every pipeline row; NULL/NULL/
    # NULL/False/False is the truth for the direct callers (the test suite,
    # scripts/, /query's foreign-session refusal). Stored verbatim.
    provider: Optional[str] = None,
    upstream_model: Optional[str] = None,
    provider_trust: Optional[str] = None,
    pii_input_relaxed: bool = False,
    usage_estimated: bool = False,
    # PRD-021 STORY-009 (F7, D14, D17). The first two are REQUIRED, like
    # _deny's discipline fields: a pipeline arm that forgets them must be a
    # TypeError, not a row that claims the reply was buffered. The bare `*`
    # keeps them keyword-only so no positional caller can shift. The other two
    # default to the truth of a row with no divergence and no realtime stream.
    *,
    streamed_realtime: bool,
    reasoning_shown: bool,
    stream_redaction_divergence: bool = False,
    completion_id: Optional[str] = None,
    # PRD-022 F8 / D10: verbatim passthrough, all None on a row that does not
    # set them (a pre-step-7 row has no attempt and no route_model).
    request_id: Optional[str] = None,
    attempt: Optional[int] = None,
    route_model: Optional[str] = None,
    fallback_reason: Optional[str] = None,
    skipped_providers: Optional[str] = None,
    cache_read_tokens: Optional[int] = None,
    cache_write_tokens: Optional[int] = None,
    # PRD-018 D13. Step 8 of a request with tool decisions only: a journaled
    # row carries its decisions in the SAME journal entry, so the callable gets
    # the row's write_id and returns the decision rows keyed `<write_id>:<i>`.
    # It runs only on the journal path (the healthy path builds no extra rows)
    # and every other caller leaves it None.
    journal_decisions: Optional[
        Callable[[str], Sequence[ActionDecisionRow]]
    ] = None,
) -> AuditRef:
    entry = AuditLog(
        timestamp=datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT),
        user_id=user_id,
        device=device,
        prompt_hash=hash_prompt(prompt),
        prompt_preview=prompt[:_PREVIEW_LENGTH],
        response_hash=hash_prompt(response) if response is not None else None,
        response_preview=response[:_PREVIEW_LENGTH] if response is not None else None,
        model_used=model_used,
        tokens_used=tokens_used,
        was_duplicate_blocked=was_duplicate_blocked,
        suspicious_pattern=suspicious_pattern,
        success=success,
        error_message=error_message,
        pii_detected_input=pii_detected_input,
        pii_detected_output=pii_detected_output,
        pii_entities=",".join(pii_entities) if pii_entities else None,
        role=role,
        denied_permission=denied_permission,
        session_id=session_id,
        dedup_key=dedup_key,
        pattern_role=pattern_role,
        pattern_action=pattern_action,
        profile=profile,
        ingress=ingress,
        message_count=message_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        streamed=streamed,
        has_tool_calls=has_tool_calls,
        conversation_key=conversation_key,
        limit_exceeded=limit_exceeded,
        ignored_params=ignored_params,
        provider=provider,
        upstream_model=upstream_model,
        provider_trust=provider_trust,
        pii_input_relaxed=pii_input_relaxed,
        usage_estimated=usage_estimated,
        streamed_realtime=streamed_realtime,
        reasoning_shown=reasoning_shown,
        stream_redaction_divergence=stream_redaction_divergence,
        completion_id=completion_id,
        request_id=request_id,
        attempt=attempt,
        route_model=route_model,
        fallback_reason=fallback_reason,
        skipped_providers=skipped_providers,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        # PRD-018 D4 (Section 6.4): minted once per call, beside the one
        # timestamp stamp and before the first attempt, so every retry (and,
        # from STORY-008, the journal entry and the drain) carries the same
        # pair.
        write_id=_new_write_id(),
    )
    # PRD-018 F7, D13: only a StorageUnavailableError (retry budget spent,
    # retry refused, breaker open) is journaled. A STATEMENT failure or any
    # other StorageError is a bug or a bad row, not an outage, and propagates
    # as before. When the append fails (journal full or broken, or none open)
    # AuditUnavailableError propagates: nothing is released without a record
    # (D10, T5). The unit of work has already logged the driver text through
    # database._redacted(), so nothing driver-shaped is logged here.
    try:
        audit_id = insert_audit_log(entry)
    except StorageUnavailableError:
        decisions = (
            tuple(journal_decisions(entry.write_id))
            if journal_decisions is not None
            else ()
        )
        audit_journal.append(entry, decisions)
        logger.warning(
            "audit row journaled: user_id=%s write_id=%s decisions=%d",
            user_id,
            entry.write_id,
            len(decisions),
        )
        return AuditRef(None, entry.write_id)
    return AuditRef(audit_id, entry.write_id)
