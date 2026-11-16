import uuid
from typing import TYPE_CHECKING, Any, List, Literal, Optional, Union

from pydantic import BaseModel, PrivateAttr, field_validator

if TYPE_CHECKING:
    from app.services.tool_release import ToolOutcome


class QueryRequest(BaseModel):
    # Deprecated (PRD-005 Section 10): accepted for backward compatibility
    # only. Never trusted as identity -- the audited user id always comes
    # from the authenticated credential. A value that doesn't match the
    # credential is refused with 403 rather than silently overridden.
    user_id: Optional[str] = None
    prompt: str
    device: Optional[str] = None
    model: str = "gpt-4"
    openrouter_api_key: Optional[str] = None
    # The conversation this send belongs to (PRD-008 Section 10). Optional and
    # defaulted, so a client written against the previous release is unaffected:
    # omitting it writes NULL to the audit column and behaves exactly as before.
    #
    # A `str` and deliberately not `uuid.UUID`. The value round-trips to a TEXT
    # audit column and travels to ChatState as a string, and a type that
    # serializes differently on the way out would be a second representation of
    # the same id (STORY-010 Technical Notes).
    session_id: Optional[str] = None

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: Optional[str]) -> Optional[str]:
        """A canonical UUID4 string when present, or a 422 (PRD-008 STORY-010).

        Three properties, each deliberate:

        **`None` passes through untouched.** A request that omits the field must
        behave exactly as the current release does, so absence is not a case
        this validator has an opinion about.

        **Version 4.** `database.create_chat_session` mints `str(uuid.uuid4())`
        and takes no caller-supplied id, so a v1 id -- which carries a MAC
        address and a timestamp -- is not one this system ever issued.

        **The canonical spelling, via `str(parsed) == value`.** `{braces}`,
        `urn:uuid:` and uppercase hex all parse, and all are a *second
        representation of the same id*. That matters most in the one case
        nothing downstream would catch: with transcript persistence off the
        ownership check is a no-op and this value goes straight into the audit
        column, so an uppercase id would be filed under a spelling no
        `WHERE session_id = ?` will ever match. The alternative -- normalizing
        to `str(parsed)` -- is rejected because the id is written *as supplied*,
        and normalizing would edit the caller's value on the way past.
        """
        if value is None:
            return None

        try:
            parsed = uuid.UUID(value)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError(
                f"session_id must be a canonical lowercase UUID4 string, got {value!r}. "
                "Session ids are minted by the harness and echoed back unchanged; "
                "omit the field entirely to send without a session."
            ) from exc

        if parsed.version != 4 or str(parsed) != value:
            raise ValueError(
                f"session_id must be a canonical lowercase UUID4 string, got {value!r}. "
                "Session ids are minted by the harness and echoed back unchanged; "
                "omit the field entirely to send without a session."
            )

        return value


class QuerySuccessResponse(BaseModel):
    status: Literal["SUCCESS"] = "SUCCESS"
    response: str
    audit_id: int
    model_used: str
    tokens_used: int
    pii_redacted: bool = False
    pii_entities_masked: List[str] = []

    # PRD-017 STORY-010 DD-1: step 7c's `tool_release.ToolOutcome`, set by the
    # pipeline only when the upstream returned tool calls; `None` means no call
    # was evaluated. A private attribute, not a field: never serialized and
    # absent from the JSON schema, so `/query`'s body and OpenAPI do not move
    # (D17). Typed `Any` so this module imports nothing from `app`. Pydantic's
    # `__eq__` compares private attributes too, so two results are equal only
    # when both carry the same outcome (or neither does).
    _tool_outcome: Any = PrivateAttr(default=None)

    @property
    def tool_outcome(self) -> "Optional[ToolOutcome]":
        return self._tool_outcome


class QueryBlockedDuplicateResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    first_query_at: str


class QueryBlockedSuspiciousResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    pattern: str


class QueryBlockedForbiddenResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    required_permission: str


class QueryBlockedContextLimitResponse(BaseModel):
    """A conversation refused for being over a configured context limit (PRD-010 D2).

    `limit` names *which* configured maximum was hit, and only ever one is
    reported: `run_conversation` checks messages first and returns on the
    first breach, so a conversation over both is reported as `messages`. That is
    deliberate -- a caller shortening a conversation to fit the message count
    will be told about the character count on the next attempt, and a body that
    named both would imply the two were measured independently when the second
    was never reached.

    `maximum` is the configured limit as read for *that call*
    (`CONTEXT_MAX_MESSAGES` / `CONTEXT_MAX_CHARACTERS`), not a constant: it is
    echoed back so a client can see the bound it broke without reading the
    server's configuration.

    `redaction_characters` is the third maximum, PII redaction's (PRD-012
    Section 6.7, D4). Only a PII policy with `max_characters` set (`code`)
    reports it, from step 6, after both context limits have passed, so it is
    never reported alongside them. Its `maximum` is that policy's
    `max_characters` (`PII_MAX_CHARACTERS_CODE`) for that call, and `actual`
    counts only what the analyzer would process: covered roles, fenced blocks
    blanked, newlines not counted.
    """

    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    limit: Literal["messages", "characters", "redaction_characters"]
    maximum: int
    actual: int


class QueryBlockedUsageLimitResponse(BaseModel):
    """An authorized attempt refused for being over a usage limit (PRD-013 Section 6.7).

    `200` with a `BLOCKED` body on `/query`, like every other block there, and
    never `429` (D5): the `403` the brief mentions is the `/v1` mapping, and
    PRD-014 owns it. The body distinguishes the two limits and carries
    `resets_at` so that mapping can choose per limit.

    Only one limit is reported: the rate is checked first and the budget only
    if the rate passed, the rule `QueryBlockedContextLimitResponse` follows.
    `maximum` is the limit the identity was held to for that call (its
    override, else its role's entry, else `*`). `actual` is the count in the
    current minute's window for `requests` and the tokens used today for
    `tokens`. `resets_at` is UTC in the audit timestamp format: the end of the
    minute for `requests`, the next 00:00 UTC for `tokens`, both derived from
    the database's clock, never the instance's.
    """

    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    limit: Literal["requests", "tokens"]
    maximum: int
    actual: int
    resets_at: str


QueryResponse = Union[
    QuerySuccessResponse,
    QueryBlockedDuplicateResponse,
    QueryBlockedSuspiciousResponse,
    QueryBlockedForbiddenResponse,
    QueryBlockedContextLimitResponse,
    # Last, so every existing member keeps its position in this plain union.
    QueryBlockedUsageLimitResponse,
]


class AuditQueryEntry(BaseModel):
    audit_id: int
    user_id: str
    timestamp: str
    model: Optional[str] = None
    prompt_hash: str
    was_duplicate_blocked: bool
    suspicious_pattern_detected: bool
    device: Optional[str] = None
    pii_detected_input: bool = False
    pii_detected_output: bool = False
    pii_entities: List[str] = []
    role: Optional[str] = None
    denied_permission: Optional[str] = None
    # The conversation this row came from (PRD-008 Section 5, story 8). The
    # column has been written since STORY-008 and threaded since STORY-009;
    # this is where it becomes readable, so that three rows that were one
    # conversation are visibly one conversation instead of a guess.
    #
    # Optional and defaulted because `None` is the honest answer for two whole
    # classes of row: everything written before this PRD, and every send that
    # carried no session (`POST /query` without the field, which PRD Section 3
    # promises keeps working). A required field here would break every existing
    # constructor, this file's tests included.
    #
    # No validator, deliberately. This is a *read* model: the value was already
    # checked as a canonical UUID4 at the write end by `QueryRequest`
    # (STORY-010), and revalidating on the way out would refuse to report rows
    # the database legitimately holds.
    session_id: Optional[str] = None
    # PRD-011 D6: which role the matched message had (`user`, `tool`, `system`,
    # `assistant`) and what the policy did with it (`block` or `flag`).
    # `suspicious_pattern_detected` above keeps its meaning -- "a pattern was
    # matched" -- and is therefore true for a flag too; `pattern_action` is the
    # field that tells the two cases apart.
    #
    # Optional, defaulted and unvalidated for `session_id`'s reasons: both are
    # NULL on every row without a pattern and on every row written before
    # PRD-011. A NULL action on a row that has a pattern means a block, which
    # is how the `blocked_suspicious` counters read it.
    pattern_role: Optional[str] = None
    pattern_action: Optional[str] = None
    # PRD-012 D9: the profile that ran (`chat`, `code`, or a custom name).
    # Under `code`, `pii_detected_output = False` means the response was not
    # analyzed, not that it was clean; this field is what says so. Optional,
    # defaulted and unvalidated for `session_id`'s reasons: NULL on every row
    # written before PRD-012 and on /query's foreign-session refusal.
    profile: Optional[str] = None
    # PRD-013 Sections 6.2 and 6.10: which door the request came through, how
    # big it was, what it cost, whether it was streamed or carried tool calls,
    # which conversation it belongs to, and which usage limit refused it.
    #
    # Optional, defaulted and unvalidated for `session_id`'s reasons. The six
    # nullable ones are NULL on every row written before PRD-013, and the two
    # token fields are also NULL when no upstream call was made or the
    # provider omitted the split. The two flags default to `False` rather than
    # `None` because the columns are `NOT NULL DEFAULT 0`: 0 is true of every
    # older row, since neither was possible then.
    #
    # `conversation_key` is a grouping aid; `session_id` stays authoritative
    # for chat rows. `dedup_key` is still not exposed (PRD-009 D5). A row with
    # `limit_exceeded` set is `success=true`, as a duplicate block is.
    ingress: Optional[str] = None
    message_count: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    streamed: bool = False
    has_tool_calls: bool = False
    conversation_key: Optional[str] = None
    limit_exceeded: Optional[str] = None
    # PRD-015 Section 10: the client parameter names `/v1` did not forward,
    # sorted and comma-joined. Optional, defaulted and unvalidated for
    # `session_id`'s reasons: NULL on every `/query` and chat row and on every
    # row written before PRD-015.
    ignored_params: Optional[str] = None


class AuditResponse(BaseModel):
    total: int
    queries: List[AuditQueryEntry]


class ActionClassificationEntry(BaseModel):
    # PRD-016 Section 6.10: the decoded form of one element of the
    # `classifications` JSON column, as `action_audit._classifications_json`
    # writes it. `kind` is null when the classifier reported no operation
    # (`tool.unknown`, `tool.malformed`).
    rule: str
    kind: Optional[str] = None
    detail: str


class ActionDecisionEntry(BaseModel):
    # PRD-016 F11 / Section 10: one `action_decisions` row, with exactly the
    # fields of the Section 10 example, in its order.
    #
    # `arguments_preview` and `arguments_hash` are deliberately absent (Section
    # 10), for the reason PRD-009 D5 gives for `dedup_key`: they are storage
    # aids, not something a reader of the audit needs. `session_id` is absent
    # too, because the Section 10 example omits it (orchestrator decision,
    # STORY-016 plan Q1).
    #
    # `reason` is the stored column, returned as stored and never rebuilt
    # (orchestrator decision, STORY-014/015 plans; PRD 6.10 amended).
    #
    # A read model with no validators, for `AuditQueryEntry.session_id`'s
    # reasons: the values were checked at the write end.
    id: int
    timestamp: str
    audit_id: Optional[int] = None
    user_id: str
    role: str
    tool_call_id: str
    tool_name: str
    operation_kind: Optional[str] = None
    target_preview: Optional[str] = None
    decision: str
    rule: str
    reason: str
    granted_by: Optional[str] = None
    classifications: List[ActionClassificationEntry]
    policy_digest: str


class ActionsResponse(BaseModel):
    # PRD-016 Section 10 / F11: `entries` only. Unlike `AuditResponse` there is
    # no `total`: the PRD defines none, and `count_action_decisions()` takes no
    # `user_id`, so a scoped total would have no source (F10).
    entries: List[ActionDecisionEntry]


class StatsResponse(BaseModel):
    total_queries: int
    blocked_duplicates: int
    blocked_suspicious: int
    unique_users: int
    success_rate: str
    top_models: List[str]
    top_users: List[str]
    pii_detected_queries: int = 0
    top_pii_entities: List[str] = []
    # PRD-013 Section 6.10: sums over every row with NULL as 0, and the count
    # of usage-limit refusals (0 until STORY-011 writes any).
    input_tokens: int = 0
    output_tokens: int = 0
    blocked_usage_limits: int = 0
    # PRD-016 F11 / Section 10: decision counts over the whole action_decisions
    # table, 0 when empty.
    actions_denied: int = 0
    actions_flagged: int = 0
    actions_allowed: int = 0
