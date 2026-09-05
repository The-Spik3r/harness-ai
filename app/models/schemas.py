import uuid
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, field_validator


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


QueryResponse = Union[
    QuerySuccessResponse,
    QueryBlockedDuplicateResponse,
    QueryBlockedSuspiciousResponse,
    QueryBlockedForbiddenResponse,
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


class AuditResponse(BaseModel):
    total: int
    queries: List[AuditQueryEntry]


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
