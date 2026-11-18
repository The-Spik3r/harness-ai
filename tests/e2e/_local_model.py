"""Helpers for the opt-in local-model E2E (PRD-020 STORY-014, D16).

Pure side of `tests/e2e/test_local_model.py`: the environment knobs and their
documented defaults, the reachability probe, the best-effort server facts and
the registry YAML written for the harness child. No fixtures live here, so the
default suite unit-tests this file (`tests/test_local_model_e2e_helpers.py`)
without a model server.

The defaults are the documented example (an LM Studio style server), never the
only option: `HARNESS_E2E_LOCAL_BASE_URL` and `HARNESS_E2E_LOCAL_MODEL` point
the run at Ollama, vLLM or any other OpenAI-compatible server.
"""

import os
from typing import Callable, Tuple

import httpx

ENV_BASE_URL = "HARNESS_E2E_LOCAL_BASE_URL"
ENV_MODEL = "HARNESS_E2E_LOCAL_MODEL"
DEFAULT_BASE_URL = "http://localhost:1235/v1"
DEFAULT_MODEL = "google/gemma-4-e4b"
PROVIDER = "local"
NOT_EXPOSED = "not exposed"


def local_config() -> Tuple[str, str]:
    """(base_url, model) from the environment, falling back to the documented defaults."""
    base_url = os.environ.get(ENV_BASE_URL, "").strip() or DEFAULT_BASE_URL
    model = os.environ.get(ENV_MODEL, "").strip() or DEFAULT_MODEL
    return base_url.rstrip("/"), model


def probe(base_url: str, model: str, get: Callable = httpx.get) -> Tuple[bool, str]:
    """(True, "") when `{base_url}/models` answers and lists `model`; else (False, reason).

    The reason names what is missing (the URL and its env var, or the model and
    its env var with the ids the server does list), so a skip is actionable.
    """
    url = f"{base_url}/models"
    try:
        response = get(url, timeout=5)
    except httpx.HTTPError as exc:
        return False, (
            f"no local model server answered at {url} ({type(exc).__name__}); "
            f"start one or set {ENV_BASE_URL}"
        )
    if response.status_code != 200:
        return False, (
            f"{url} answered HTTP {response.status_code}, not a model list; set {ENV_BASE_URL} to an "
            "OpenAI-compatible /v1 base URL"
        )
    try:
        listed = [entry["id"] for entry in response.json()["data"]]
    except (ValueError, KeyError, TypeError):
        return False, f"{url} did not return an OpenAI-style model list; set {ENV_BASE_URL}"
    if model not in listed:
        return False, (
            f"model {model!r} is not served at {base_url}; set {ENV_MODEL} to one of {listed}"
        )
    return True, ""


def _json(get: Callable, url: str):
    """The JSON body of a 200 answer, else None. Never raises."""
    try:
        response = get(url, timeout=5)
        if response.status_code != 200:
            return None
        return response.json()
    except (httpx.HTTPError, ValueError):
        return None


def server_facts(base_url: str, model: str, get: Callable = httpx.get) -> dict:
    """Best-effort server facts for the report (AC5). Never raises, never fails a test.

    Ollama: `/api/version` and the model's digest from `/api/tags`. LM Studio:
    the model's entry in `/api/v0/models` (no digest, no version). Otherwise
    "not exposed". The root is `base_url` without its trailing `/v1`.
    """
    root = base_url[: -len("/v1")] if base_url.endswith("/v1") else base_url
    facts = {"server": NOT_EXPOSED, "version": NOT_EXPOSED, "digest": NOT_EXPOSED, "model_info": {}}
    try:
        version = _json(get, f"{root}/api/version")
        if isinstance(version, dict) and "version" in version:
            facts["server"] = "ollama"
            facts["version"] = str(version["version"])
            tags = _json(get, f"{root}/api/tags")
            for entry in (tags or {}).get("models", []) if isinstance(tags, dict) else []:
                if isinstance(entry, dict) and model in (entry.get("name"), entry.get("model")):
                    facts["digest"] = str(entry.get("digest", NOT_EXPOSED))
            return facts
        listing = _json(get, f"{root}/api/v0/models")
        entries = listing.get("data", []) if isinstance(listing, dict) else []
        for entry in entries:
            if isinstance(entry, dict) and entry.get("id") == model:
                facts["server"] = "lm-studio"
                facts["model_info"] = {
                    key: entry[key]
                    for key in ("arch", "quantization", "compatibility_type", "state", "max_context_length")
                    if key in entry
                }
    except Exception:  # best effort: a malformed body is "not exposed", never a failure
        pass
    return facts


def registry_yaml(model: str, base_url: str) -> str:
    """The registry file for the harness child: one keyless, internal `local` provider (PRD-020 F1).

    `timeout_seconds: 300` covers a cold model load; no `pii: relaxed` (not needed here).
    """
    return (
        "version: 1\n"
        f"default_model: {model}\n"
        "providers:\n"
        f"  - name: {PROVIDER}\n"
        "    type: openai_compatible\n"
        f"    base_url: {base_url}\n"
        "    trust: internal\n"
        "    usage_missing: estimate\n"
        "    timeout_seconds: 300\n"
        "    models:\n"
        f"      - id: {model}\n"
        "        capabilities: {tools: true, streaming: true}\n"
    )
