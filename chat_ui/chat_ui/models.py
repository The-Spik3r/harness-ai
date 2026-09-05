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


class ChatSessionSummary(pydantic.BaseModel):
    """One row of the session rail: what it is called, and when it last moved.

    Three fields, and the absence of the rest is the design. PRD-008 Section
    6.1, verbatim: "Every session row carries a relative activity time and
    nothing else -- no message count, no model, no verdict summary... a figure
    belongs in the rail only if the reader needs it to choose a row, and they
    do not." Adding one here removes that decision rather than improving the
    model, the way a preview field would on `admin_models.AuditRow`.

    `pydantic.BaseModel`, not `rx.Base`: `rx.Base` does not exist in the pinned
    `reflex==0.9.6.post1` (it was the pydantic-v1 shim, and Reflex 0.9.x is
    pydantic-v2 based). `ChatMessage` above and both models in
    `admin_models.py` subclass `pydantic.BaseModel` for the same reason and
    render fine under `rx.foreach`.
    """

    session_id: str = ""
    title: str = ""
    # Humanized activity time, precomputed in the backend: component functions
    # only ever see Vars, so datetime math cannot run at render. A field rather
    # than a computed property for PRD-006's derived-once row model --
    # components read fields; they do not compute. Never stored: a persisted
    # "2m ago" is wrong the moment it is read back, so `format_activity`
    # recomputes it on every load.
    activity_info: str = ""
