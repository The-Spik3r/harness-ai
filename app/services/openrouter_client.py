from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "gpt-4"
_TIMEOUT_SECONDS = 30.0


class OpenRouterError(Exception):
    pass


@dataclass
class OpenRouterResult:
    response: str
    model_used: str
    tokens_used: int


def call_openrouter(
    prompt: str,
    model: str = _DEFAULT_MODEL,
    api_key: Optional[str] = None,
    client: Optional[httpx.Client] = None,
) -> OpenRouterResult:
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
        "messages": [{"role": "user", "content": prompt}],
    }

    owns_client = client is None
    http_client = client or httpx.Client(timeout=_TIMEOUT_SECONDS)
    try:
        try:
            resp = http_client.post(_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            tokens_used = data["usage"]["total_tokens"]
        except (KeyError, IndexError, ValueError) as exc:
            raise OpenRouterError(
                f"OpenRouter returned an unexpected response shape: {exc}"
            ) from exc
    finally:
        if owns_client:
            http_client.close()

    return OpenRouterResult(response=content, model_used=model, tokens_used=tokens_used)
