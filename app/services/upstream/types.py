"""Types shared by the upstream package (PRD-020 6.4, 6.5).

Separate from `__init__` so the adapter can raise `UpstreamError` without an
import cycle. `UpstreamError` and `UpstreamResult` are the former
OpenRouterError / OpenRouterResult, unchanged (PRD-020 D12).
"""

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

from app.models.messages import Message, ToolCallSpec
from app.services.upstream.params import GenerationParams, ToolParams


class UpstreamError(Exception):
    """A failed upstream call, and what the client knows about why (PRD-015 D7).

    upstream_status is the HTTP status the upstream answered with, None when
    there was no response. retryable is True only for a transient fault --
    timeout, transport error, upstream 5xx or 429 -- since the same request
    may then succeed; STORY-011 maps it to `/v1`'s retry semantics. The
    message is the only positional argument, so `str(exc)` -- and with it the
    audit row's error_message and /query's 502 detail -- is unchanged.
    """

    def __init__(
        self,
        message: str,
        *,
        upstream_status: Optional[int] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.upstream_status = upstream_status
        self.retryable = retryable



@dataclass
class UpstreamResult:
    response: str
    model_used: str
    tokens_used: int
    # PRD-013 STORY-003: usage.prompt_tokens and usage.completion_tokens, None
    # when the provider omitted or malformed the field. Declared after
    # tokens_used with defaults so three-argument construction keeps working.
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    # PRD-015 STORY-002: choices[0].finish_reason, None when absent or not a
    # string. Declared last with a default for the same reason as the split.
    finish_reason: Optional[str] = None
    # PRD-017 STORY-004: choices[0].message.tool_calls, parsed only when the
    # request sent tools= (D18). Declared last with a default, the PRD-013 /
    # PRD-015 precedent, so three-argument construction keeps working.
    tool_calls: tuple[ToolCallSpec, ...] = ()



@dataclass(frozen=True)
class UpstreamRequest:
    """What an adapter is asked to send (PRD-020 6.4): the upstream id, not the requested one."""

    messages: Sequence[Message]
    upstream_model: str
    params: Optional[GenerationParams] = None
    tools: Optional[ToolParams] = None


class ProviderAdapter(Protocol):
    """One wire protocol (PRD-020 6.4). STORY-013 adds streaming; only `complete` exists now."""

    def complete(self, request: UpstreamRequest, api_key: Optional[str]) -> UpstreamResult: ...
