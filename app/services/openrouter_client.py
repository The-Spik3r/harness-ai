from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Union

import httpx

from app.config import settings
from app.models.messages import Message

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "gpt-4"

_ALLOWED_GENERATION_PARAMS = frozenset({"temperature", "max_tokens", "top_p", "stop"})
_MAX_STOP_SEQUENCES = 4


class OpenRouterError(Exception):
    pass


class UnsupportedParameterError(Exception):
    """A generation parameter is outside PRD-010's allowlist or its validated range.

    Raised by GenerationParams construction (direct or via from_mapping), always
    before any HTTP call -- PRD-010 T5: no ingress may widen OpenRouter's
    surface past four allowlisted, range-checked fields.
    """


@dataclass(frozen=True)
class GenerationParams:
    """The only generation parameters call_openrouter may forward (PRD-010 F3, T5).

    Every field defaults to None and is sent only when set. from_mapping is
    PRD-014's entry point; nothing in this PRD calls it in production.
    """

    temperature: Optional[float] = None   # 0.0 <= t <= 2.0
    max_tokens: Optional[int] = None       # >= 1
    top_p: Optional[float] = None          # 0.0 < p <= 1.0
    stop: Optional[Union[str, Sequence[str]]] = None   # <= 4 sequences

    def __post_init__(self) -> None:
        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            raise UnsupportedParameterError(
                f"temperature must be between 0.0 and 2.0, got {self.temperature!r}"
            )
        if self.max_tokens is not None:
            # bool is a subclass of int: True/False must not slip past >= 1.
            if isinstance(self.max_tokens, bool) or self.max_tokens < 1:
                raise UnsupportedParameterError(
                    f"max_tokens must be an integer >= 1, got {self.max_tokens!r}"
                )
        if self.top_p is not None and not (0.0 < self.top_p <= 1.0):
            raise UnsupportedParameterError(
                f"top_p must be greater than 0.0 and at most 1.0, got {self.top_p!r}"
            )
        if self.stop is not None:
            if isinstance(self.stop, str):
                pass
            elif isinstance(self.stop, (list, tuple)):
                if len(self.stop) > _MAX_STOP_SEQUENCES:
                    raise UnsupportedParameterError(
                        f"stop must have at most {_MAX_STOP_SEQUENCES} sequences, got {len(self.stop)}"
                    )
                if not all(isinstance(s, str) for s in self.stop):
                    raise UnsupportedParameterError(
                        f"stop sequences must all be strings, got {self.stop!r}"
                    )
            else:
                raise UnsupportedParameterError(
                    f"stop must be a string or a list of up to {_MAX_STOP_SEQUENCES} strings, got {self.stop!r}"
                )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "GenerationParams":
        """PRD-014's entry point. Raises for any key outside the allowlist, sorted."""
        unsupported = sorted(set(raw) - _ALLOWED_GENERATION_PARAMS)
        if unsupported:
            raise UnsupportedParameterError(
                f"unsupported parameter(s): {', '.join(unsupported)}"
            )
        return cls(**{key: raw[key] for key in _ALLOWED_GENERATION_PARAMS if key in raw})


@dataclass
class OpenRouterResult:
    response: str
    model_used: str
    tokens_used: int


def call_openrouter(
    messages: Sequence[Message],
    model: str = _DEFAULT_MODEL,
    api_key: Optional[str] = None,
    params: Optional[GenerationParams] = None,
    client: Optional[httpx.Client] = None,
) -> OpenRouterResult:
    if not messages:
        raise OpenRouterError("messages must not be empty")

    resolved_key = api_key or settings.OPENROUTER_API_KEY
    if not resolved_key:
        raise OpenRouterError(
            "OpenRouter API key not configured: pass openrouter_api_key or set OPENROUTER_API_KEY"
        )

    headers = {
        "Authorization": f"Bearer {resolved_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
    }
    if params is not None:
        for field in ("temperature", "max_tokens", "top_p", "stop"):
            value = getattr(params, field)
            if value is not None:
                payload[field] = value

    owns_client = client is None
    http_client = client or httpx.Client(timeout=settings.OPENROUTER_TIMEOUT_SECONDS)
    try:
        try:
            resp = http_client.post(_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc

        try:
            data = resp.json()
            choice = data["choices"][0]
            message = choice["message"]
            content = message["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise OpenRouterError(
                f"OpenRouter returned an unexpected response shape: {exc}"
            ) from exc

        if content is None:
            finish_reason = choice.get("finish_reason")
            error_message = f"OpenRouter returned no text content (finish_reason={finish_reason})"
            if message.get("tool_calls") is not None:
                error_message += "; tool calls are not supported (PRD-016)"
            raise OpenRouterError(error_message)

        try:
            tokens_used = data["usage"]["total_tokens"]
        except (KeyError, IndexError, ValueError) as exc:
            raise OpenRouterError(
                f"OpenRouter returned an unexpected response shape: {exc}"
            ) from exc
    finally:
        if owns_client:
            http_client.close()

    return OpenRouterResult(response=content, model_used=model, tokens_used=tokens_used)
