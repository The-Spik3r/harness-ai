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
    # Was this bubble read back from the database, or has it just arrived?
    #
    # The only field here that is about *presentation* rather than about the
    # turn, and it earns the exception by being the one thing a component
    # cannot work out for itself. PRD-008 Section 6.1: "Switching sessions does
    # not animate... the skill's warning that 'extra animation contributes to
    # the feeling that the design is AI-generated' applies hardest to the
    # operation a user will perform thirty times a day."
    #
    # PRD-004's `.hx-entry` runs on *mount*, and a restored transcript mounts
    # every bubble the previous one did not have -- so before this field a
    # switch animated part of the conversation into place. Measured, not
    # assumed: switching a 2-message chat for a 5-message one fired exactly
    # three `animationstart` events, for the three bubbles React had to mount.
    #
    # **Per message, and never toggled.** The obvious alternative -- one
    # "suppress animations" flag on ChatState, switched off again after the
    # restore -- has a retrigger bug that is worse than the defect: re-enabling
    # animation on already-mounted nodes starts it on all of them, so the next
    # send would animate the whole transcript. A discriminator that is decided
    # once, when the bubble is built, and never changes for that bubble cannot
    # do that. `_to_chat_message` sets it; nothing else ever writes it.
    restored: bool = False


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
