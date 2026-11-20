"""Upstream calls, routed by the provider registry (PRD-020 6.4, 6.5, D10).

`call_upstream` is `call_openrouter` with its exact signature: it resolves the
model to a provider, picks the key (D10), and hands the request to the
provider's adapter. The old OpenRouter client module is a shim of aliases onto this
package (D12).
"""

import dataclasses
from typing import Callable, Iterator, Optional, Sequence

import httpx

from app.models.messages import Message
from app.services import provider_registry
from app.services.upstream.anthropic import AnthropicAdapter, dropped_params as _anthropic_dropped_params
from app.services.upstream.collect import collect
from app.services.upstream.openai_compatible import OpenAICompatibleAdapter
from app.services.upstream.params import (
    GenerationParams,
    ToolParams,
    UnsupportedParameterError,
)
from app.services.upstream.types import (
    ChainExhausted,
    Finish,
    ProviderAdapter,
    ReasoningDelta,
    TextDelta,
    ToolCallDelta,
    UpstreamError,
    UpstreamEvent,
    UpstreamRequest,
    UpstreamResult,
    UsageReport,
)

__all__ = [
    "AnthropicAdapter",
    "ChainExhausted",
    "Finish",
    "GenerationParams",
    "OpenAICompatibleAdapter",
    "ProviderAdapter",
    "ReasoningDelta",
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
    "stream_upstream",
]

_DEFAULT_MODEL = "gpt-4"


def _resolve_call(
    messages: Sequence[Message], model: str, api_key: Optional[str]
) -> tuple[provider_registry.Route, Optional[str]]:
    """The route and the key for one call, shared by `call_upstream` and `stream_upstream` (D10)."""
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
            # PRD-022 6.2: a provider with no usable key is `misconfigured` (D8).
            raise UpstreamError(
                f"{provider.label} API key not configured: {hint}",
                provider=provider.name,
                kind="misconfigured",
            )
    return route, key


# Adapter per registry provider type (PRD-022 D4). `client` is the openai_compatible
# adapter's injectable httpx client; the SDK-based adapter builds its own.
_ADAPTER_FACTORIES: dict[
    str, Callable[[provider_registry.Provider, Optional[httpx.Client]], ProviderAdapter]
] = {
    "openai_compatible": lambda provider, client: OpenAICompatibleAdapter(provider, client),
    "anthropic": lambda provider, client: AnthropicAdapter(provider),
}


def _build_adapter(
    provider: provider_registry.Provider, client: Optional[httpx.Client]
) -> ProviderAdapter:
    # Indexed, not `.get`: the registry vocabulary is closed, so a gap must be loud.
    return _ADAPTER_FACTORIES[provider.type](provider, client)


def dropped_params_for(route: provider_registry.Route, request: UpstreamRequest) -> tuple[str, ...]:
    """Bare names of the params `request` set that `route`'s adapter would not send (PRD-022 6.5).

    The realtime path reports what `complete()` reports on `UpstreamResult`;
    dispatching here keeps the pipeline free of provider types. A provider
    type that drops nothing returns `()`.
    """
    if route.provider.type == "anthropic":
        return _anthropic_dropped_params(request, route.model)
    return ()


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
    route, key = _resolve_call(messages, model, api_key)
    adapter = _build_adapter(route.provider, client)
    result = adapter.complete(UpstreamRequest(messages, route.upstream_model, params, tools, route.model), key)
    # model_used stays the requested id (PRD-020 D13), whatever went upstream.
    return dataclasses.replace(result, model_used=model)


def stream_upstream(
    messages: Sequence[Message],
    model: str = _DEFAULT_MODEL,
    api_key: Optional[str] = None,
    params: Optional[GenerationParams] = None,
    client: Optional[httpx.Client] = None,
    *,
    tools: Optional[ToolParams] = None,
) -> Iterator[UpstreamEvent]:
    """The answer as normalized events (PRD-021 6.2): `call_upstream`'s routing, streamed.

    A plain function: the route and the key are resolved, and their errors
    raised, at call time; the network is touched on the first `next()`. Reasoning
    is mapped only for a route whose model declares `reasoning` (OD1: legacy
    mode never does).
    """
    route, key = _resolve_call(messages, model, api_key)
    return _build_adapter(route.provider, client).stream(
        UpstreamRequest(messages, route.upstream_model, params, tools, route.model),
        key,
        reasoning=route.capabilities.reasoning,
    )
