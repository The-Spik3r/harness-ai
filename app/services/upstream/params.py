"""Generation and tool parameters for upstream calls (PRD-020 6.5, moved from the former OpenRouter client).

Moved unchanged: PRD-010 F3/T5 (allowlisted, range-checked generation params)
and PRD-017 D11 (the tool request).
"""

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Union

_ALLOWED_GENERATION_PARAMS = frozenset({"temperature", "max_tokens", "top_p", "stop"})
_MAX_STOP_SEQUENCES = 4


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
    PRD-015's entry point (the track's "PRD-014"): v1_translate.translate_request
    is its production caller.
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
        """PRD-015's entry point (`/v1`). Raises for any key outside the allowlist, sorted."""
        unsupported = sorted(set(raw) - _ALLOWED_GENERATION_PARAMS)
        if unsupported:
            raise UnsupportedParameterError(
                f"unsupported parameter(s): {', '.join(unsupported)}"
            )
        return cls(**{key: raw[key] for key in _ALLOWED_GENERATION_PARAMS if key in raw})


@dataclass(frozen=True)
class ToolParams:
    """The tool request call_openrouter forwards (PRD-017 Section 4, D11).

    Its own keyword, not fields on GenerationParams (PRD-010 T5: from_mapping
    must keep refusing `tools`). Carries values only: shape validation is the
    `/v1` translator's (STORY-008), which is its one builder. Fields are sent
    as given, and a None field is not sent.
    """

    tools: Sequence[Mapping[str, Any]]
    tool_choice: Optional[Union[str, Mapping[str, Any]]] = None
    parallel_tool_calls: Optional[bool] = None

