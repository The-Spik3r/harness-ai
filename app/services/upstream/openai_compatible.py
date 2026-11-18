"""The OpenAI-compatible adapter (PRD-020 6.4, F3, F6, T7).

Today's `call_openrouter` body, parameterized by a `Provider`: base URL, label
and timeout come from the provider; the key arrives only as an argument and
goes only into the request headers (T1, T6). No registry access, no settings.
`complete()` and `stream()` (PRD-020 D11) share one payload builder, one
redirect/HTTP-error classification and, through `reply.py`, one set of reply
rules.
"""

from typing import Any, Iterator, Optional

import httpx

from app.models.messages import Message
from app.services.provider_registry import Provider
from app.services.upstream.reply import (  # noqa: F401 - re-exported: moved to reply.py (STORY-013)
    _parse_tool_calls,
    _resolve_usage,
    _token_count,
    result_from_reply,
)
from app.services.upstream.sse import parse_events
from app.services.upstream.types import (
    Finish,
    UpstreamError,
    UpstreamEvent,
    UpstreamRequest,
    UpstreamResult,
)


def _wire_message(message: Message) -> dict[str, Any]:
    """One Message as the upstream wire shape (PRD-017 F5).

    Tool-free messages stay exactly {"role", "content"}. arguments is the
    ToolCallSpec's string, never parsed or re-serialized (D13).
    """
    wire: dict[str, Any] = {"role": message.role}
    if message.tool_call_id is not None:
        wire["tool_call_id"] = message.tool_call_id
    # OpenAI's tool-call assistant turn is content: null; the normalizer turned
    # that null into "" (messages.py), so it is restored here.
    wire["content"] = None if message.tool_calls and message.content == "" else message.content
    if message.tool_calls:
        wire["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in message.tool_calls
        ]
    return wire


def _classify_http_error(exc: httpx.HTTPError) -> tuple[Optional[int], bool]:
    """(upstream_status, retryable) for a failed request (PRD-015 Section 7.5)."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status, status >= 500 or status == 429
    # Timeouts, connect errors and the other transport failures: no response,
    # and nothing about the request made it fail.
    if isinstance(exc, httpx.TransportError):
        return None, True
    return None, False


class OpenAICompatibleAdapter:
    """POST {base_url}/chat/completions for one provider (PRD-020 6.4)."""

    def __init__(self, provider: Provider, client: Optional[httpx.Client] = None) -> None:
        self._provider = provider
        self._client = client

    @staticmethod
    def _headers(api_key: Optional[str], *, stream: bool = False) -> dict[str, str]:
        # No key (a keyless provider) means no Authorization header at all (PRD-020 F3).
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        headers["Content-Type"] = "application/json"
        if stream:
            headers["Accept"] = "text/event-stream"
        return headers

    @staticmethod
    def _payload(request: UpstreamRequest, *, stream: bool = False) -> dict[str, Any]:
        params = request.params
        tools = request.tools
        payload: dict[str, Any] = {
            "model": request.upstream_model,
            "messages": [_wire_message(m) for m in request.messages],
        }
        if params is not None:
            for field in ("temperature", "max_tokens", "top_p", "stop"):
                value = getattr(params, field)
                if value is not None:
                    payload[field] = value
        # PRD-017 D11: forwarded as given, a None field not sent.
        if tools is not None:
            payload["tools"] = tools.tools
            for field in ("tool_choice", "parallel_tool_calls"):
                value = getattr(tools, field)
                if value is not None:
                    payload[field] = value
        if stream:
            # PRD-020 D11: ask for the usage chunk, so a streamed answer is billed like a whole one.
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _open_client(self) -> httpx.Client:
        # PRD-020 D5/F3: redirects are never followed, so a provider cannot bounce
        # the request (and its Authorization header) to another host.
        return self._client or httpx.Client(
            timeout=self._provider.timeout_seconds, follow_redirects=False
        )

    def _url(self) -> str:
        return f"{self._provider.base_url.rstrip('/')}/chat/completions"

    @staticmethod
    def _raise_for_response(resp: httpx.Response, label: str) -> None:
        # Checked here, not via raise_for_status alone: whether httpx treats a 3xx
        # as an error varies by version. The Location is never quoted.
        if 300 <= resp.status_code < 400:
            raise UpstreamError(
                f"{label} request failed: unexpected redirect (HTTP {resp.status_code}); "
                "redirects are not followed",
                upstream_status=resp.status_code,
                retryable=False,
            )
        resp.raise_for_status()

    @staticmethod
    def _http_error(exc: httpx.HTTPError, label: str) -> UpstreamError:
        upstream_status, retryable = _classify_http_error(exc)
        return UpstreamError(
            f"{label} request failed: {exc}",
            upstream_status=upstream_status,
            retryable=retryable,
        )

    def complete(self, request: UpstreamRequest, api_key: Optional[str]) -> UpstreamResult:
        provider = self._provider
        label = provider.label
        headers = self._headers(api_key)
        payload = self._payload(request)

        owns_client = self._client is None
        http_client = self._open_client()
        try:
            try:
                resp = http_client.post(self._url(), headers=headers, json=payload)
                self._raise_for_response(resp, label)
            except httpx.HTTPError as exc:
                raise self._http_error(exc, label) from exc

            try:
                data = resp.json()
            except ValueError as exc:
                raise UpstreamError(
                    f"{label} returned an unexpected response shape: {exc}"
                ) from exc
            return result_from_reply(provider, request, data)
        finally:
            if owns_client:
                http_client.close()

    def stream(
        self, request: UpstreamRequest, api_key: Optional[str], *, reasoning: bool = False
    ) -> Iterator[UpstreamEvent]:
        """The answer as normalized events (PRD-020 D11).

        A generator: the request is sent, and every error raised, on the first
        `next()`. It owns the client and the response and closes both when the
        generator ends, is closed early or fails. `reasoning` opts the parser into
        `ReasoningDelta` (PRD-021 Risk 3). A stream that ends without a `Finish`
        event is a non-retryable shape error (PRD-021 F2).
        """
        label = self._provider.label
        headers = self._headers(api_key, stream=True)
        payload = self._payload(request, stream=True)

        owns_client = self._client is None
        http_client = self._open_client()
        try:
            try:
                with http_client.stream("POST", self._url(), headers=headers, json=payload) as resp:
                    # A non-2xx body is never read: raise_for_status needs only the status line.
                    self._raise_for_response(resp, label)
                    finished = False
                    for event in parse_events(resp.iter_lines(), label, reasoning=reasoning):
                        if isinstance(event, Finish):
                            finished = True
                        yield event
                    if not finished:
                        raise UpstreamError(
                            f"{label} returned an unexpected response shape: "
                            "stream ended without a finish reason"
                        )
            except httpx.HTTPError as exc:
                raise self._http_error(exc, label) from exc
        finally:
            if owns_client:
                http_client.close()
