from typing import List, Literal, Optional, Union

from pydantic import BaseModel


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
