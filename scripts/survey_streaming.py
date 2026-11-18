"""What do providers stream, and what does the parser keep? Measured with tiny live requests.

PRD-021 STORY-001, serving PRD Sections 6.2, 8, 15 "Not verified" and O5. This is a
spike: it *records* facts and asserts none of them, like `scripts/spike_pii_placeholders.py`.
It calls real servers, so it is not a CI test and its file name keeps pytest from
ever collecting it (tests/test_survey_streaming.py covers only the offline helpers).

At most `MAX_REQUESTS` streamed requests are sent in one run (`max_tokens` 64,
`stream: true`, `stream_options.include_usage: true`):

    1. an OpenRouter reasoning model (`--reasoning-model`)
    2. an OpenRouter non-reasoning model (`--model`)
    3. the local OpenAI-compatible server (`--local-base`), skipped when it does not answer
    +  spare calls: the reasoning model again with `reasoning: {"effort": "low"}` only
       when the first call streamed no reasoning; one retry on a transient fault or a
       404 model id (`--fallback-reasoning-model`).

Each response is saved as a sanitized fixture `<out-dir>/<provider>-<model-slug>.sse`:
only `data:` lines, strings under `delta.content|reasoning|reasoning_content` and
`reasoning_details[].text|summary` cut to 40 characters, ids/model/finish_reason/usage
kept, SSE comment lines dropped, no headers. The API key lives only in the
`Authorization` header; any text that could echo it passes through `scrub()` first.

Every saved line is then replayed through `app.services.upstream.sse.parse_events` to
report which events it yields and which delta keys it drops.

Without a key or without network it prints a message and exits 0.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

# Importing the upstream package pulls Settings; dummies keep this script
# independent of the project's .env (the key it uses is read below, not from there).
os.environ.setdefault("OPENROUTER_API_KEY", "survey-dummy")
os.environ.setdefault("ADMIN_TOKEN", "survey-dummy")

import httpx  # noqa: E402

MAX_REQUESTS = 6
MAX_TOKENS = 64
TRUNCATE_AT = 40
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
LOCAL_BASE = "http://localhost:1235/v1"
LOCAL_MODEL = "google/gemma-4-e4b"
PROMPT = "Reply with one word: hello."

_TEXT_KEYS = ("content", "reasoning", "reasoning_content")
_DETAIL_KEYS = ("text", "summary")
_STANDARD_DELTA_KEYS = frozenset({"role", "content", "tool_calls", "refusal", "function_call"})

_requests_sent = 0


class RequestBudgetExceeded(RuntimeError):
    """A run asked for more than `MAX_REQUESTS` calls."""


def _take_request() -> None:
    global _requests_sent
    if _requests_sent >= MAX_REQUESTS:
        raise RequestBudgetExceeded(f"refusing request {_requests_sent + 1}: budget is {MAX_REQUESTS}")
    _requests_sent += 1


def scrub(text: str, key: Optional[str]) -> str:
    """`text` with the key replaced by [KEY]."""
    if key and key in text:
        return text.replace(key, "[KEY]")
    return text


def _cut(value: Any) -> Any:
    return value[:TRUNCATE_AT] if isinstance(value, str) else value


def sanitize_line(line: str, key: Optional[str]) -> Optional[str]:
    """The fixture form of one SSE line, or None to drop it (comments, non-data, blanks)."""
    if not line.startswith("data:"):
        return None
    # Scrub before cutting: a cut must not leave half a key behind.
    value = scrub(line[5:].lstrip(" "), key)
    if value.strip() == "[DONE]":
        return "data: [DONE]"
    try:
        chunk = json.loads(value)
    except ValueError:
        return None
    if isinstance(chunk, dict):
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") if isinstance(choice, dict) else None
            if not isinstance(delta, dict):
                continue
            for k in _TEXT_KEYS:
                if k in delta:
                    delta[k] = _cut(delta[k])
            for detail in delta.get("reasoning_details") or []:
                if isinstance(detail, dict):
                    for k in _DETAIL_KEYS:
                        if k in detail:
                            detail[k] = _cut(detail[k])
    return scrub("data: " + json.dumps(chunk, ensure_ascii=False), key)


def summarize(lines: Iterable[str]) -> dict[str, Any]:
    """Facts of one saved stream (sanitized `data:` lines), parser view included."""
    from app.services.upstream.sse import parse_events

    lines = list(lines)
    reasoning_keys: set[str] = set()
    other_keys: set[str] = set()
    usage_keys: list[str] = []
    usage_choices_empty: Optional[bool] = None
    reasoning_tokens: Any = None
    first_reasoning = first_content = None
    for i, line in enumerate(lines):
        if not line.startswith("data:") or line.endswith("[DONE]"):
            continue
        chunk = json.loads(line[5:].lstrip(" "))
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            for k, v in delta.items():
                if k.startswith("reasoning"):
                    reasoning_keys.add(k)
                    if v and first_reasoning is None:
                        first_reasoning = i
                elif k not in _STANDARD_DELTA_KEYS:
                    other_keys.add(k)
            if delta.get("content") and first_content is None:
                first_content = i
        usage = chunk.get("usage")
        if isinstance(usage, dict):
            usage_keys = sorted(usage)
            usage_choices_empty = not chunk.get("choices")
            details = usage.get("completion_tokens_details")
            if isinstance(details, dict):
                reasoning_tokens = details.get("reasoning_tokens")
    counts: dict[str, int] = {}
    for event in parse_events(lines, "survey"):
        name = type(event).__name__
        counts[name] = counts.get(name, 0) + 1
    # Keys parse_events reads: content, tool_calls (delta); finish_reason; usage.
    dropped = sorted(reasoning_keys | other_keys | {"role"} & _delta_keys(lines))
    return {
        "reasoning_fields": sorted(reasoning_keys),
        "other_delta_keys": sorted(other_keys),
        "reasoning_before_content": (
            None if first_reasoning is None or first_content is None else first_reasoning < first_content
        ),
        "streamed_reasoning": first_reasoning is not None,
        "usage_keys": usage_keys,
        "usage_chunk_choices_empty": usage_choices_empty,
        "reasoning_tokens": reasoning_tokens,
        "parse_events": counts,
        "delta_keys_dropped_by_parser": dropped,
    }


def _delta_keys(lines: Iterable[str]) -> set[str]:
    keys: set[str] = set()
    for line in lines:
        if line.startswith("data:") and not line.endswith("[DONE]"):
            for choice in json.loads(line[5:].lstrip(" ")).get("choices") or []:
                keys |= set((choice.get("delta") or {}).keys())
    return keys


def slug(provider: str, model: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", f"{provider}-{model}".lower()).strip("-")


def load_key(env_file: str) -> Optional[str]:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key and key != "survey-dummy":
        return key
    try:
        from dotenv import dotenv_values

        key = dotenv_values(env_file).get("OPENROUTER_API_KEY")
    except Exception:
        key = None
    return key or None


class ProbeFailed(Exception):
    def __init__(self, status: Optional[int], message: str):
        super().__init__(message)
        self.status = status


def probe(base: str, key: Optional[str], model: str, extra: Optional[dict] = None, timeout: float = 60.0):
    """One streamed request. Returns (raw lines, saw_comment). Counts against the budget."""
    _take_request()
    body = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": MAX_TOKENS,
        "stream": True,
        "stream_options": {"include_usage": True},
        **(extra or {}),
    }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    lines: list[str] = []
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", f"{base}/chat/completions", json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    text = _error_message(resp.read().decode("utf-8", "replace"), key)
                    raise ProbeFailed(resp.status_code, f"HTTP {resp.status_code}: {text}")
                for line in resp.iter_lines():
                    lines.append(line)
    except httpx.HTTPError as exc:
        raise ProbeFailed(None, scrub(f"{type(exc).__name__}", key)) from None
    return lines


def _error_message(body: str, key: Optional[str]) -> str:
    """Only the provider's message text (no ids), scrubbed and short."""
    try:
        msg = json.loads(body)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        msg = "unparsable error body"
    return scrub(str(msg), key)[:120]


def reachable(base: str) -> bool:
    try:
        httpx.get(f"{base}/models", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


def save(out_dir: Path, provider: str, model: str, raw: list[str], key: Optional[str]) -> tuple[Path, list[str], bool]:
    kept = [s for s in (sanitize_line(line, key) for line in raw) if s is not None]
    comments = any(line.startswith(":") for line in raw)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slug(provider, model)}.sse"
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return path, kept, comments


def report(label: str, path: Path, kept: list[str], comments: bool) -> None:
    print(f"\n== {label} -> {path.as_posix()} ({len(kept)} data lines, keep-alive comments: {comments})")
    for k, v in summarize(kept).items():
        print(f"   {k}: {v}")


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--reasoning-model", default="deepseek/deepseek-r1-0528")
    p.add_argument("--fallback-reasoning-model", default="deepseek/deepseek-v4-flash")
    p.add_argument("--model", default="openai/gpt-4o-mini")
    p.add_argument("--no-local", action="store_true")
    p.add_argument("--local-base", default=LOCAL_BASE)
    p.add_argument("--out-dir", default="tests/fixtures/prd021_survey")
    p.add_argument("--env-file", default=".env")
    p.add_argument("--already-used", type=int, default=0,
                   help="requests sent by earlier runs of this survey; counts toward the budget")
    args = p.parse_args(argv)

    global _requests_sent
    _requests_sent = args.already_used
    key = load_key(args.env_file)
    if not key:
        print("survey: no OPENROUTER_API_KEY (env or --env-file); nothing sent, nothing written.")
        return 0
    out = Path(args.out_dir)
    used: list[str] = []

    def run(provider, base, model, label, extra=None, k=None):
        raw = probe(base, k, model, extra)
        path, kept, comments = save(out, provider, model, raw, key)
        used.append(f"{provider}:{model}{' +' + json.dumps(extra) if extra else ''}")
        report(label, path, kept, comments)
        return kept

    try:
        model = args.reasoning_model
        try:
            kept = run("openrouter", OPENROUTER_BASE, model, "OpenRouter reasoning model", k=key)
        except ProbeFailed as exc:
            print(f"survey: {model} failed ({exc}); one retry with {args.fallback_reasoning_model}")
            model = args.fallback_reasoning_model
            kept = run("openrouter", OPENROUTER_BASE, model, "OpenRouter reasoning model (fallback)", k=key)
        if not summarize(kept)["streamed_reasoning"]:
            kept = run("openrouter", OPENROUTER_BASE, model, "OpenRouter reasoning model, effort=low",
                       extra={"reasoning": {"effort": "low"}}, k=key)
        run("openrouter", OPENROUTER_BASE, args.model, "OpenRouter non-reasoning model", k=key)
    except ProbeFailed as exc:
        print(f"survey: OpenRouter call failed ({exc}); stopping.")
    except RequestBudgetExceeded as exc:
        print(f"survey: {exc}")
        return 1

    if not args.no_local:
        if reachable(args.local_base):
            try:
                run("local", args.local_base, LOCAL_MODEL, "Local server")
            except ProbeFailed as exc:
                print(f"local: call failed ({exc})")
        else:
            print("local: unreachable")
    print(f"\nsurvey: {_requests_sent} request(s) sent: {used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
