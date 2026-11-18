"""Deprecated shim: aliases onto `app.services.upstream` (PRD-020 D12).

Nothing new imports this module. Existing imports, and injected stubs with the
`(messages, model, api_key, **kw)` signature, keep working.
"""

from app.services.upstream import (
    GenerationParams,
    ToolParams,
    UnsupportedParameterError,
    UpstreamError,
    UpstreamResult,
    call_upstream,
)

call_openrouter = call_upstream
OpenRouterError = UpstreamError
OpenRouterResult = UpstreamResult

__all__ = [
    "GenerationParams",
    "OpenRouterError",
    "OpenRouterResult",
    "ToolParams",
    "UnsupportedParameterError",
    "call_openrouter",
]
