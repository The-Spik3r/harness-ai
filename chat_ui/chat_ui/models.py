import pydantic


class ChatMessage(pydantic.BaseModel):
    """Typed chat message model carrying kind discriminator and metadata."""

    kind: str
    content: str
    prompt: str = ""
    model_used: str = ""
    tokens_used: int = 0
    audit_id: int = 0
    pii_redacted: bool = False
    pii_entities: list[str] = []
    pattern: str = ""
    first_query_at: str = ""
    detail: str = ""
