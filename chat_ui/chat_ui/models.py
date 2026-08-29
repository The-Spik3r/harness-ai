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
    required_permission: str = ""
    first_query_at: str = ""
    # Humanized duplicate copy, precomputed in the backend: component
    # functions only ever see Vars, so datetime math cannot run at render.
    duplicate_relative_info: str = ""
    duplicate_release_info: str = ""
    detail: str = ""
