"""The `/v1` wire shapes (PRD-015 Sections 7.1, 7.4-7.7).

One definition of what the OpenAI-compatible ingress reads and writes: the
Chat Completions request, the completion, the stream chunk, the model list and
the error object. Pure on purpose: no I/O, no settings, no `app` import. The
translator (`v1_translate`), the router and the SSE writer build these; the
mapping rules live there, not here. `/query`'s shapes stay in `schemas.py`.

Serialize with `model_dump(mode="json")` or `model_dump_json()`, never with
`exclude_none=True`: the PRD examples carry `null`s (`logprobs`,
`finish_reason`, `param`, `harness`) that clients read, and the only keys that
disappear are the two Section 7.6 omits, dropped by their own serializers.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, model_serializer

CHAT_COMPLETION_ID_PREFIX = "chatcmpl-harness-"


def chat_completion_id(audit_id: int) -> str:
    """The completion id for an audit row (PRD-015 Section 7.4).

    Derived from the audit id so a client log line leads to the row. The body,
    the `X-Harness-Audit-Id` header and every stream chunk call this function,
    so the three can never spell it differently.
    """
    return f"{CHAT_COMPLETION_ID_PREFIX}{audit_id}"


class ChatCompletionRequest(BaseModel):
    """`POST /v1/chat/completions` as parsed, before classification (Section 7.1).

    Only `model`, `messages` and `stream` are typed. Every other field is
    `Optional[Any]` on purpose: STORY-006 classifies each value and reports a
    400 naming its `param`, and a pydantic type here would refuse `"hot"` as a
    temperature first, with a vaguer error. Absent and an explicit `null` are
    told apart through `model_fields_set`.

    `messages` items stay raw: the normalizer judges them, not pydantic.

    `extra="allow"` keeps every unknown key in `model_extra`, so classification
    sees what was sent instead of what survived parsing. `openrouter_api_key`,
    `session_id` and `user_id` are deliberately not declared: on this ingress
    they are unknown keys and ignored like any other (BYOK is out, Section 4).
    """

    model_config = ConfigDict(extra="allow")

    model: str
    messages: List[Any]
    stream: bool = False
    # Only `include_usage` is honoured; other sub-keys are recorded as ignored.
    stream_options: Optional[Any] = None

    # Forwarded through GenerationParams.from_mapping (`max_completion_tokens`
    # as `max_tokens`).
    temperature: Optional[Any] = None
    top_p: Optional[Any] = None
    max_tokens: Optional[Any] = None
    stop: Optional[Any] = None
    max_completion_tokens: Optional[Any] = None

    # Rejected unless absent or the default (Section 7.1's table).
    n: Optional[Any] = None
    logprobs: Optional[Any] = None
    top_logprobs: Optional[Any] = None
    response_format: Optional[Any] = None
    tools: Optional[Any] = None
    tool_choice: Optional[Any] = None
    functions: Optional[Any] = None
    function_call: Optional[Any] = None
    modalities: Optional[Any] = None
    audio: Optional[Any] = None

    # Never identity or device (D1); its name is recorded in ignored_params.
    user: Optional[Any] = None


# The values Section 7.4 names, each one the OpenAI SDK's own Literal accepts.
# Anything else the upstream reports is the translator's to map to "stop".
FinishReason = Literal["stop", "length", "content_filter"]


class Usage(BaseModel):
    """Token counts as the client sees them (Section 7.4).

    When the provider omitted the prompt/completion split, both are `0` and
    `total_tokens` is still the reported total: emitting the keys keeps clients
    that compute cost from them working. The audit row keeps `NULL`, which stays
    the truth.
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class Choice(BaseModel):
    index: int = 0
    message: AssistantMessage
    logprobs: None = None
    finish_reason: FinishReason


class HarnessCompletionInfo(BaseModel):
    """The `harness` extension object on a success (Section 7.4).

    The OpenAI SDK keeps unknown fields (`model_extra`), so clients that do not
    know it ignore it. The fields are `QuerySuccessResponse`'s.
    """

    audit_id: int
    pii_redacted: bool = False
    pii_entities_masked: List[str] = []


class ChatCompletion(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage
    harness: HarnessCompletionInfo


class ChunkDelta(BaseModel):
    role: Optional[Literal["assistant"]] = None
    content: Optional[str] = None

    @model_serializer(mode="wrap")
    def _drop_unset(self, handler):
        # Section 7.6: the finish chunk's delta is `{}`, not
        # `{"role": null, "content": null}`.
        return {key: value for key, value in handler(self).items() if value is not None}


class ChunkChoice(BaseModel):
    index: int = 0
    delta: ChunkDelta
    # `null` on the content chunk, the reason on the finish chunk.
    finish_reason: Optional[FinishReason] = None


class ChatCompletionChunk(BaseModel):
    """One `data:` event of a buffered stream (Section 7.6).

    Content and finish chunks carry no `usage` key; the usage chunk (only with
    `include_usage`) carries `choices: []` and `usage`. Every chunk's `id` is
    `chat_completion_id(audit_id)`.
    """

    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: List[ChunkChoice]
    usage: Optional[Usage] = None

    @model_serializer(mode="wrap")
    def _drop_absent_usage(self, handler):
        data = handler(self)
        if data.get("usage") is None:
            data.pop("usage", None)
        return data


class ModelEntry(BaseModel):
    """One `GET /v1/models` entry (Section 7.7). `created` is unknown, so `0`."""

    id: str
    object: Literal["model"] = "model"
    created: int = 0
    owned_by: str


class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: List[ModelEntry]


# The four in Section 7.5. No `rate_limit_error`: the harness never sends 429
# (PRD-013 D5), and a 404 `model_not_found` is an `invalid_request_error`.
ErrorType = Literal[
    "invalid_request_error",
    "authentication_error",
    "permission_error",
    "api_error",
]


class ErrorDetail(BaseModel):
    """The OpenAI error object plus the harness's own fields (Section 7.5).

    `message` names the rule that failed and never echoes message content.
    `code` is a plain string: the codes are the translator's table, not this
    schema's. `harness` carries the pipeline response's own fields, and is
    `null` (the key kept, like `param`) when no pipeline response exists, as for
    a request-translation failure.
    """

    message: str
    type: ErrorType
    param: Optional[str] = None
    code: str
    harness: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """An error body, and also the payload of a post-commit SSE `error` event (Section 7.6)."""

    error: ErrorDetail
