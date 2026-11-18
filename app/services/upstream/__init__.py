"""Upstream calls, routed by the provider registry (PRD-020 6.4, 6.5, D10).

`call_upstream` is `call_openrouter` with its exact signature: it resolves the
model to a provider, picks the key (D10), and hands the request to the
provider's adapter. The old OpenRouter client module is a shim of aliases onto this
package (D12).
"""

import dataclasses
from typing import Optional, Sequence

import httpx

from app.models.messages import Message
from app.services import provider_registry
from app.services.upstream.collect import collect
from app.services.upstream.openai_compatible import OpenAICompatibleAdapter
from app.services.upstream.params import (
    GenerationParams,
    ToolParams,
    UnsupportedParameterError,
)
from app.services.upstream.types import (
    Finish,
    ProviderAdapter,
    TextDelta,
    ToolCallDelta,
    UpstreamError,
    UpstreamEvent,
    UpstreamRequest,
    UpstreamResult,
    UsageReport,
)

__all__ = [
    "Finish",
    "GenerationParams",
    "OpenAICompatibleAdapter",
    "ProviderAdapter",
    "TextDelta",
    "ToolCallDelta",
    "ToolParams",
    "UnsupportedParameterError",
    "UpstreamError",
    "UpstreamEvent",
    "UpstreamRequest",
    "UpstreamResult",
    "UsageReport",
    "call_upstream",
    "collect",
]

_DEFAULT_MODEL = "gpt-4"


def call_upstream(
    messages: Sequence[Message],
    model: str = _DEFAULT_MODEL,
    api_key: Optional[str] = None,
    params: Optional[GenerationParams] = None,
    client: Optional[httpx.Client] = None,
    *,
    tools: Optional[ToolParams] = None,
) -> UpstreamResult:
    """tool_calls are parsed only when `tools=` was sent (PRD-017 D18).

    Without it, a null content with tool calls stays today's error. `api_key`
    is the caller's own key: used only for a `byok` provider (PRD-020 D10);
    otherwise the provider's own key, or none for a keyless provider.
    """
    if not messages:
        raise UpstreamError("messages must not be empty")

    route = provider_registry.resolve(model)
    if route is None:
        raise UpstreamError("No provider route for the requested model")
    provider = route.provider

    key: Optional[str] = None
    if provider.key_env is not None:
        key = api_key if (api_key and provider.byok) else provider_registry.api_key_for(provider)
        if not key:
            hint = (
                f"pass openrouter_api_key or set {provider.key_env}"
                if provider.byok
                else f"set {provider.key_env}"
            )
            raise UpstreamError(f"{provider.label} API key not configured: {hint}")

    adapter = OpenAICompatibleAdapter(provider, client)
    result = adapter.complete(UpstreamRequest(messages, route.upstream_model, params, tools), key)
    # model_used stays the requested id (PRD-020 D13), whatever went upstream.
    return dataclasses.replace(result, model_used=model)
