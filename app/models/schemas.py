from typing import List, Literal, Optional, Union

from pydantic import BaseModel


class QueryRequest(BaseModel):
    user_id: str
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


class QueryBlockedDuplicateResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    first_query_at: str


class QueryBlockedSuspiciousResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    pattern: str


QueryResponse = Union[
    QuerySuccessResponse, QueryBlockedDuplicateResponse, QueryBlockedSuspiciousResponse
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
