"""Do fixed PII placeholders make a coding agent unusable? Measured with a live model.

PRD-012 STORY-012, serving PRD Section 7 (F10), Section 9.2 (T8), Risk 7 and
Decision D5. This is a spike: it *records* outcomes and asserts none of them,
exactly as `scripts/measure_pii_latency.py` does. It calls a real model through
OpenRouter, so it is not a CI test and its file name keeps pytest from ever
collecting it (tests/test_spike_pii_placeholders.py pins that).

A tiny agent loop runs three scripted tasks over files from
`tests/corpora/pii/code/` (edit a fixture, write a test, rename a field). The
model gets four text tools. Its reply is parsed, the tool is applied to an
in-memory workspace of the **raw** files, and the tool result goes back as the
next `user` turn. Every send goes through the real
`run_conversation(profile="code")`, so step 6 masks exactly what a PRD-014
client's traffic would get. Four arms:

    a        -- fixed `<TYPE>`: production, unpatched
    b        -- indexed per request `<TYPE_n>`, numbered by first appearance
                across the conversation; no stored mapping, renumbered every send
    c        -- reversible: `<TYPE_n>` from an in-memory mapping kept for the
                task's conversation, restored in the response before the
                pipeline returns it
    control  -- PII redaction patched off: not an option, the baseline that
                separates "the model cannot do this" from "placeholders stopped it"

**How (b) and (c) are produced.** `query_pipeline._redact` is swapped for a
scheme that runs `pii_redactor`'s own span pipeline (fence blanking, analysis,
overlaps, structure-safe runs, JSON clipping, post-condition) and changes only
the placeholder string. That couples this script to `pii_redactor` privates on
purpose: a copy could drift and measure something else, and the parity test
fails loudly if the privates change shape. The mappings live only here. Nothing
is persisted and no production module gains one (STORY-012 Technical Notes).

**Why tool results are unfenced `user` turns.** Step 0 refuses `tool` turns
until PRD-016, and under `code` fenced blocks are skipped (D2), so a fenced file
read would carry no placeholder and test nothing. The tool protocol is
Cline-style XML tags, also unfenced, so the assistant turns fed back as history
are redacted too (T7), as they are for a real text-protocol agent.

**Why every task-run has its own user id.** Step 4's duplicate check keys on
the user and the raw conversation. A task's first turn is identical in every arm
and run, so a shared id would get BLOCKED_DUPLICATE from the second arm onward.
The conversation text is never altered to dodge it.

**Every value sent is synthetic** (tests/corpora/pii/SOURCES.md: reserved
domains, 555-01xx numbers, published test PANs and IBANs), which is what makes
the control arm acceptable.

This script writes audit rows. It refuses a non-local `DATABASE_URL` unless
told otherwise. The OpenRouter key is read from the environment or `.env`,
never from a flag, and a test dummy is refused.

Usage:

    python scripts/spike_pii_placeholders.py --model anthropic/claude-sonnet-4.5
    python scripts/spike_pii_placeholders.py --model <slug> --runs 3 --json /tmp/d5.json
    python scripts/spike_pii_placeholders.py --model <slug> --arms a,c --tasks fixture
"""

import argparse
import ast
import contextlib
import importlib.metadata
import itertools
import json
import os
import platform
import re
import subprocess
import sys
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Callable, Iterator, Optional, Sequence, Union
from unittest import mock
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# `app.config.settings` is built at import time and DATABASE_URL has no default,
# so the endpoint has to be in the environment *before* the first `app.` import
# (scripts/measure_history_latency.py:69-98). Unlike that script, the OpenRouter
# key is deliberately not defaulted: a dummy would reach a real upstream.
_DEFAULT_ENDPOINT = "http://127.0.0.1:8080"


def _database_url(argv: Optional[Sequence[str]]) -> str:
    """--database-url, else HARNESS_TEST_LIBSQL_URL, else the dev server.

    Never `.env`'s DATABASE_URL: that is the deployment's database, and this
    script writes audit rows.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    for index, item in enumerate(args):
        if item == "--database-url" and index + 1 < len(args):
            return args[index + 1]
        if item.startswith("--database-url="):
            return item.split("=", 1)[1]
    return os.environ.get("HARNESS_TEST_LIBSQL_URL") or _DEFAULT_ENDPOINT


def _bootstrap_environment(argv: Optional[Sequence[str]] = None) -> str:
    endpoint = _database_url(argv)
    os.environ["DATABASE_URL"] = endpoint
    # Required by Settings() and irrelevant here: no admin route is exercised.
    os.environ.setdefault("ADMIN_TOKEN", "spike-admin-token")
    return endpoint


_ENDPOINT = _bootstrap_environment()

from app.config import settings  # noqa: E402
from app.db import database  # noqa: E402
from app.models.messages import Message  # noqa: E402
from app.models.schemas import QuerySuccessResponse  # noqa: E402
from app.services import authz, pattern_config, pii_policy, pii_redactor, query_pipeline  # noqa: E402
from app.services.identity import Identity  # noqa: E402
from app.services.openrouter_client import (  # noqa: E402
    GenerationParams,
    OpenRouterError,
    OpenRouterResult,
    call_openrouter,
)
from app.services.pattern_detector import strip_fenced_blocks  # noqa: E402
from app.services.pii_policy import PiiPolicy, get_pii_policy  # noqa: E402
from app.services.pii_redactor import PiiRedactorError  # noqa: E402
from app.services.query_pipeline import run_conversation  # noqa: E402

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0"}
_DUMMY_KEYS = {"", "test-key", "measurement-stub-key", "spike-stub-key"}
_CORPUS = REPO_ROOT / "tests" / "corpora" / "pii" / "code"
_ARMS = ("control", "a", "b", "c")
_PROFILE = "code"

#: Captured at import, before any arm patches the module attribute.
_ORIGINAL_REDACT = query_pipeline._redact


# --------------------------------------------------------------------------
# Placeholder schemes
# --------------------------------------------------------------------------


class Scheme:
    """What step 6 does to one message: the signature of query_pipeline._redact."""

    arm = ""

    def begin_request(self) -> None:
        """Called once before every run_conversation send."""

    def redact(self, text: str, policy: PiiPolicy) -> tuple[str, list[str]]:
        raise NotImplementedError

    def restore(self, text: str) -> tuple[str, int]:
        """(text with placeholders restored, count of unknown indexed placeholders)."""
        return text, 0


class FixedScheme(Scheme):
    """Arm (a): production, byte for byte. The live arm runs unpatched; this
    exists so the parity test and the loop can treat every arm alike."""

    arm = "a"

    def redact(self, text, policy):
        return _ORIGINAL_REDACT(text, policy)


class ControlScheme(Scheme):
    """The baseline: nothing is masked."""

    arm = "control"

    def redact(self, text, policy):
        return text, []


#: `<TYPE_n>`, optionally quoted, as restore() finds it in a response.
_INDEXED_PLACEHOLDER = re.compile(r'("?)<([A-Z][A-Z_]*?)_(\d+)>("?)')


class IndexedScheme(Scheme):
    """Arms (b) and (c): production's spans, with `<TYPE_n>` for `<TYPE>`.

    `n` numbers the distinct original values of one type by first appearance.
    Step 6 redacts messages in order, so numbering is stable over the unchanged
    prefix of a growing conversation even when it restarts on every send.

    Non-persistent (b) clears the mapping in begin_request() and never
    restores: there is no stored mapping, only a deterministic renumbering.
    Persistent (c) keeps it for the scheme's life -- one task-run's
    conversation -- and restores responses from it.
    """

    def __init__(self, persistent: bool):
        self.persistent = persistent
        self.arm = "c" if persistent else "b"
        self._clear()

    def _clear(self) -> None:
        self._numbers: dict[tuple[str, str], int] = {}
        self._counters: dict[str, Iterator[int]] = defaultdict(lambda: itertools.count(1))
        # placeholder -> (original bytes, the original was a whole JSON number token)
        self._originals: dict[str, tuple[str, bool]] = {}

    def begin_request(self) -> None:
        if not self.persistent:
            self._clear()

    def _placeholder(self, entity_type: str, original: str, number_token: bool) -> str:
        key = (entity_type, original)
        if key not in self._numbers:
            self._numbers[key] = next(self._counters[entity_type])
        placeholder = f"<{entity_type}_{self._numbers[key]}>"
        self._originals.setdefault(placeholder, (original, number_token))
        return placeholder

    def redact(self, text, policy):
        if not policy.structure_safe:
            return _ORIGINAL_REDACT(text, policy)
        if not settings.PII_REDACTION_ENABLED or not text:
            return text, []

        # app/services/pii_redactor.py:redact_for_policy, with one change: the
        # replacement string of every range.
        analysis = strip_fenced_blocks(text) if policy.skip_fenced_blocks else text
        # PRD-012 STORY-013 F-4: JSON escapes are spaces for the analyzer.
        is_json = pii_redactor._is_json_document(text)
        if is_json:
            analysis = pii_redactor._blank_escapes(text, analysis)
        accepted = pii_redactor._resolve_overlaps(pii_redactor._analyze(analysis, policy))
        if not accepted:
            return text, []
        json_tokens = pii_redactor._json_tokens(text) if is_json else None
        ranges = pii_redactor._replacement_ranges(text, analysis, accepted, json_tokens)

        indexed = []
        for start, end, replacement, entity_type in ranges:
            # A JSON number token is replaced whole by `"<TYPE>"`, quoted.
            number_token = replacement.startswith('"')
            placeholder = self._placeholder(entity_type, text[start:end], number_token)
            indexed.append((start, end, f'"{placeholder}"' if number_token else placeholder, entity_type))

        redacted = pii_redactor._splice(text, indexed)
        entities = sorted({entity_type for _, _, _, entity_type in indexed})
        if json_tokens is not None:
            try:
                json.loads(redacted)
            except (ValueError, RecursionError) as exc:
                raise PiiRedactorError("redaction would produce invalid JSON") from exc
        return redacted, entities

    def restore(self, text):
        if not self.persistent:
            return text, 0
        unresolved = 0

        def substitute(match: re.Match) -> str:
            nonlocal unresolved
            opening, entity_type, number, closing = match.groups()
            hit = self._originals.get(f"<{entity_type}_{number}>")
            if hit is None:
                unresolved += 1
                return match.group(0)
            original, number_token = hit
            if number_token and opening and closing:
                return original  # `"<PHONE_NUMBER_1>"` was a bare number token
            return f"{opening}{original}{closing}"

        return _INDEXED_PLACEHOLDER.sub(substitute, text), unresolved


def make_scheme(arm: str) -> Scheme:
    return {
        "a": FixedScheme,
        "control": ControlScheme,
        "b": lambda: IndexedScheme(persistent=False),
        "c": lambda: IndexedScheme(persistent=True),
    }[arm]()


def placeholder_pattern(entities: Sequence[str]) -> re.Pattern:
    """`<TYPE>` or `<TYPE_n>` for the policy's entities plus the NER types, so
    a model echoing `<PERSON>` of its own accord is counted too."""
    names = sorted(set(entities) | set(pii_redactor._NER_ENTITY_TYPES), key=len, reverse=True)
    return re.compile(r"<(?:" + "|".join(map(re.escape, names)) + r")(?:_\d+)?>")


@contextlib.contextmanager
def scheme_installed(scheme: Scheme) -> Iterator[None]:
    """Arm (a) runs production untouched; every other arm replaces step 6's call."""
    if isinstance(scheme, FixedScheme):
        yield
        return
    with mock.patch.object(query_pipeline, "_redact", scheme.redact):
        yield


# --------------------------------------------------------------------------
# Tool protocol and workspace
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a coding agent working in a small repository. You act only through tools.

Reply with exactly one tool call per message, written as plain text in these tags. Do not wrap tool calls in Markdown code fences.

<read_file><path>relative/path</path></read_file>
  Returns the file's current contents.

<replace_in_file><path>relative/path</path><old>exact existing text</old><new>replacement text</new></replace_in_file>
  Replaces one occurrence of the old text. The old text must match the file exactly, including whitespace, and must occur exactly once.

<write_file><path>relative/path</path><content>full file contents</content></write_file>
  Creates or overwrites the whole file.

<done/>
  Call this when the task is complete.

Read a file before you change it. You may write a short sentence before the tool call, but nothing after it."""

_TOOL_ARGUMENTS = {
    "read_file": ("path",),
    "replace_in_file": ("path", "old", "new"),
    "write_file": ("path", "content"),
    "done": (),
}
_TOOL_OPEN = re.compile(r"<(read_file|replace_in_file|write_file|done)\s*(/?)>")


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict


@dataclass(frozen=True)
class ParseError:
    message: str


def _trim(value: str) -> str:
    """One leading and one trailing newline, the ones the tag layout adds."""
    if value.startswith("\r\n"):
        value = value[2:]
    elif value.startswith("\n"):
        value = value[1:]
    if value.endswith("\r\n"):
        value = value[:-2]
    elif value.endswith("\n"):
        value = value[:-1]
    return value


def parse_tool_call(reply: str) -> Union[ToolCall, ParseError]:
    """The first tool call in `reply`.

    Only the four tool names open a call, and argument tags are looked up by
    their own names, so `<EMAIL_ADDRESS_1>` inside an argument is plain text.
    The last argument closes at its *last* closing tag before the call's own,
    so file content may itself contain the argument's closing tag once.
    """
    opening = _TOOL_OPEN.search(reply)
    if opening is None:
        return ParseError("no tool call found; reply with exactly one tool call")
    name = opening.group(1)
    if name == "done":
        return ToolCall("done", {})
    if opening.group(2):
        return ParseError(f"<{name}/> needs arguments")

    body_start = opening.end()
    close = reply.rfind(f"</{name}>", body_start)
    if close == -1:
        return ParseError(f"missing </{name}>")

    arguments = {}
    cursor = body_start
    names = _TOOL_ARGUMENTS[name]
    for position, argument in enumerate(names):
        tag = f"<{argument}>"
        start = reply.find(tag, cursor, close)
        if start == -1:
            return ParseError(f"<{name}> is missing <{argument}>")
        start += len(tag)
        end_tag = f"</{argument}>"
        last = position == len(names) - 1
        end = reply.rfind(end_tag, start, close) if last else reply.find(end_tag, start, close)
        if end == -1:
            return ParseError(f"<{name}> is missing </{argument}>")
        arguments[argument] = _trim(reply[start:end])
        cursor = end + len(end_tag)
    arguments["path"] = arguments["path"].strip()
    return ToolCall(name, arguments)


def _normalise_path(path: str) -> str:
    path = path.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


@dataclass
class ToolOutcome:
    result: str
    done: bool = False
    replace_miss: bool = False


class Workspace:
    """The raw files. What the model writes is stored as written, placeholders and all."""

    def __init__(self, files: dict[str, str]):
        self.files = {_normalise_path(path): content for path, content in files.items()}

    def apply(self, call: ToolCall) -> ToolOutcome:
        if call.name == "done":
            return ToolOutcome("ok", done=True)
        path = _normalise_path(call.arguments["path"])
        if call.name == "read_file":
            if path not in self.files:
                return ToolOutcome(f"error: no such file: {path}")
            # The raw content, unfenced and with no header line, as a real
            # agent's tool turn carries it: step 6 analyzes it (F-5), and a JSON
            # file gets production's JSON-aware mode, which a header would defeat.
            return ToolOutcome(self.files[path])
        if call.name == "write_file":
            self.files[path] = call.arguments["content"]
            return ToolOutcome(f"[tool_result write_file path={path}] ok")
        # replace_in_file, against the raw file
        if path not in self.files:
            return ToolOutcome(f"error: no such file: {path}")
        old = call.arguments["old"]
        occurrences = self.files[path].count(old) if old else 0
        if occurrences == 0:
            return ToolOutcome(f"error: old text not found in {path}", replace_miss=True)
        if occurrences > 1:
            return ToolOutcome(f"error: old text is not unique in {path} ({occurrences} matches)")
        self.files[path] = self.files[path].replace(old, call.arguments["new"], 1)
        return ToolOutcome(f"[tool_result replace_in_file path={path}] ok")


# --------------------------------------------------------------------------
# Tasks and their checkers
# --------------------------------------------------------------------------

Check = Callable[[dict[str, str], re.Pattern], tuple[bool, str]]


@dataclass(frozen=True)
class Task:
    id: str
    instruction: str
    sources: dict[str, str]  # workspace path -> corpus file name
    target: str
    check: Check

    def files(self) -> dict[str, str]:
        return {path: (_CORPUS / name).read_text(encoding="utf-8") for path, name in self.sources.items()}


def _placeholder_failure(content: str, pattern: re.Pattern) -> Optional[str]:
    found = pattern.findall(content)
    return f"{len(found)} placeholder(s) in the artifact, e.g. {found[0]}" if found else None


def _check_fixture(files, pattern):
    content = files.get("fixtures/seed-users.json")
    if content is None:
        return False, "fixtures/seed-users.json is missing"
    placeholder = _placeholder_failure(content, pattern)
    if placeholder:
        return False, placeholder
    try:
        actual = json.loads(content)
    except ValueError as exc:
        return False, f"invalid JSON: {exc}"
    expected = json.loads((_CORPUS / "seed-users.json").read_text(encoding="utf-8"))
    for user in expected["users"]:
        if user["username"] == "pobrien":
            user["active"] = False
    if actual != expected:
        return False, "parsed document differs from the expected edit"
    return True, "ok"


def first_customer_contact() -> tuple[str, str]:
    """(email, phone) of CUSTOMERS[0] in the corpus's billing_seed.py, read with
    ast so the checker cannot drift from the file."""
    tree = ast.parse((_CORPUS / "billing_seed.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "CUSTOMERS":
            first = node.value.elts[0]
            keywords = {keyword.arg: keyword.value.value for keyword in first.keywords if isinstance(keyword.value, ast.Constant)}
            return keywords["email"], keywords["phone"]
    raise RuntimeError("CUSTOMERS not found in billing_seed.py")


def _check_test(files, pattern):
    content = files.get("tests/test_billing_contacts.py")
    if content is None:
        return False, "tests/test_billing_contacts.py was not written"
    placeholder = _placeholder_failure(content, pattern)
    if placeholder:
        return False, placeholder
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        return False, f"does not parse: {exc.msg}"
    constants = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    email, phone = first_customer_contact()
    missing = [value for value in (email, phone) if value not in constants]
    if missing:
        return False, f"{len(missing)} expected literal(s) missing"
    return True, "ok"


def _rename_key(mapping: dict, old: str, new: str) -> dict:
    """`mapping` with `old` renamed to `new` in place, key order kept."""
    return {(new if key == old else key): value for key, value in mapping.items()}


def _check_rename(files, pattern):
    import yaml

    content = files.get("deploy/staging-values.yaml")
    if content is None:
        return False, "deploy/staging-values.yaml is missing"
    placeholder = _placeholder_failure(content, pattern)
    if placeholder:
        return False, placeholder
    try:
        actual = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        return False, f"invalid YAML: {type(exc).__name__}"
    expected = yaml.safe_load((_CORPUS / "staging-values.yaml").read_text(encoding="utf-8"))
    expected["podAnnotations"] = _rename_key(expected["podAnnotations"], "oncall-phone", "oncallPhone")
    expected["env"] = _rename_key(expected["env"], "SUPPORT_CONTACT_EMAIL", "SUPPORT_EMAIL")
    if actual != expected:
        return False, "parsed document differs from the expected rename"
    return True, "ok"


# Instructions carry no PII: only file content is ever masked.
TASKS: dict[str, Task] = {
    task.id: task
    for task in (
        Task(
            id="fixture",
            instruction=(
                "Workspace files: fixtures/seed-users.json.\n"
                "In fixtures/seed-users.json, set `active` to false for the user whose "
                "username is `pobrien`. Change nothing else in the file."
            ),
            sources={"fixtures/seed-users.json": "seed-users.json"},
            target="fixtures/seed-users.json",
            check=_check_fixture,
        ),
        Task(
            id="test",
            instruction=(
                "Workspace files: billing_seed.py.\n"
                "Write tests/test_billing_contacts.py: a pytest test that imports CUSTOMERS "
                "from billing_seed and asserts that the email and the phone of the first "
                "customer in CUSTOMERS are exactly the values written in billing_seed.py, "
                "as string literals."
            ),
            sources={"billing_seed.py": "billing_seed.py"},
            target="tests/test_billing_contacts.py",
            check=_check_test,
        ),
        Task(
            id="rename",
            instruction=(
                "Workspace files: deploy/staging-values.yaml.\n"
                "In deploy/staging-values.yaml, rename the key `oncall-phone` to `oncallPhone` "
                "and the key `SUPPORT_CONTACT_EMAIL` to `SUPPORT_EMAIL`, keeping their values. "
                "Change nothing else."
            ),
            sources={"deploy/staging-values.yaml": "staging-values.yaml"},
            target="deploy/staging-values.yaml",
            check=_check_rename,
        ),
    )
}


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------


class Upstream:
    """The injected call_openrouter (query_pipeline.py forwards `params=` only
    when set). Sees what the model saw, counts placeholders both ways, and for
    (c) restores the response *before* the pipeline logs and returns it."""

    def __init__(self, real: Callable[..., OpenRouterResult], scheme: Scheme, pattern: re.Pattern):
        self.real = real
        self.scheme = scheme
        self.pattern = pattern
        self.sent_max = 0
        self.in_output = 0
        self.unresolved = 0

    def __call__(self, messages, model, api_key=None, params=None) -> OpenRouterResult:
        self.sent_max = max(self.sent_max, sum(len(self.pattern.findall(m.content)) for m in messages))
        if params is not None:
            result = self.real(messages, model=model, api_key=api_key, params=params)
        else:
            result = self.real(messages, model=model, api_key=api_key)
        self.in_output += len(self.pattern.findall(result.response))
        response, unresolved = self.scheme.restore(result.response)
        self.unresolved += unresolved
        return OpenRouterResult(response=response, model_used=result.model_used, tokens_used=result.tokens_used)


@dataclass
class TaskRun:
    arm: str
    task: str
    run: int
    correct: bool = False
    reason: str = ""
    turns: int = 0
    sent: int = 0  # placeholders in the largest request the model received
    in_output: int = 0  # placeholders across every raw model response
    in_artifact: int = 0  # placeholders in the task's target file at the end
    unresolved: int = 0  # (c) only: indexed placeholders the mapping could not restore
    replace_misses: int = 0
    parse_errors: int = 0
    aborted: Optional[str] = None
    tokens: int = 0
    transcript: list = field(default_factory=list, repr=False)


def run_task(
    task: Task,
    arm: str,
    run: int,
    *,
    model: str,
    nonce: str,
    max_turns: int,
    params: Optional[GenerationParams] = None,
    upstream_call: Callable[..., OpenRouterResult] = call_openrouter,
) -> TaskRun:
    policy = get_pii_policy(_PROFILE)
    pattern = placeholder_pattern(policy.entities)
    scheme = make_scheme(arm)  # fresh per task-run: (c)'s mapping is per conversation
    upstream = Upstream(upstream_call, scheme, pattern)
    workspace = Workspace(task.files())
    identity = Identity(user_id=f"spike012-{nonce}-{arm}-{task.id}-{run}", role="admin")
    messages = [Message("system", SYSTEM_PROMPT), Message("user", task.instruction)]
    outcome = TaskRun(arm=arm, task=task.id, run=run)

    with scheme_installed(scheme):
        for _ in range(max_turns):
            scheme.begin_request()
            try:
                result = run_conversation(
                    identity, messages, "spike012", model, None, params,
                    call_openrouter=upstream, profile=_PROFILE,
                )
            except OpenRouterError as exc:
                # The message names the HTTP failure, never request content.
                outcome.aborted = f"upstream error: {exc}"
                break
            except PiiRedactorError as exc:
                outcome.aborted = f"redaction error: {exc}"
                break
            outcome.turns += 1
            if not isinstance(result, QuerySuccessResponse):
                outcome.aborted = f"pipeline returned {result.status}: {result.reason}"
                break
            outcome.tokens += result.tokens_used or 0
            messages.append(Message("assistant", result.response))

            call = parse_tool_call(result.response)
            if isinstance(call, ParseError):
                outcome.parse_errors += 1
                messages.append(Message("user", f"error: {call.message}"))
                continue
            applied = workspace.apply(call)
            if applied.replace_miss:
                outcome.replace_misses += 1
            if applied.done:
                break
            messages.append(Message("user", applied.result))
        else:
            outcome.aborted = f"no <done/> within {max_turns} turns"

    outcome.sent = upstream.sent_max
    outcome.in_output = upstream.in_output
    outcome.unresolved = upstream.unresolved
    outcome.in_artifact = len(pattern.findall(workspace.files.get(task.target, "")))
    outcome.correct, outcome.reason = task.check(workspace.files, pattern)
    if outcome.aborted is not None:
        # The plan's rule: an aborted task-run is incorrect, even when the
        # workspace happens to pass -- the agent never finished.
        outcome.correct = False
    outcome.transcript = [{"role": m.role, "content": m.content} for m in messages]
    return outcome


# --------------------------------------------------------------------------
# Decision rules (the plan's R0-R5, written before any number was taken)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    rule: str
    outcome: str
    detail: str


def success(runs: Sequence[TaskRun], arm: str) -> Fraction:
    mine = [r for r in runs if r.arm == arm]
    return Fraction(sum(r.correct for r in mine), len(mine)) if mine else Fraction(0)


def invalid_tasks(runs: Sequence[TaskRun]) -> list[str]:
    """Tasks where arm (a) never put a placeholder in front of the model."""
    by_task = defaultdict(list)
    for r in runs:
        if r.arm == "a":
            by_task[r.task].append(r)
    return sorted(task for task, rows in by_task.items() if all(r.sent == 0 for r in rows))


def fails(runs: Sequence[TaskRun], arm: str) -> tuple[bool, str]:
    """R1's test for `arm` against control."""
    control = success(runs, "control")
    mine = success(runs, arm)
    if mine < control - Fraction(1, 3):
        return True, f"success {mine} < control {control} - 1/3"
    tasks = sorted({r.task for r in runs if r.arm == arm})
    for task in tasks:
        arm_rows = [r for r in runs if r.arm == arm and r.task == task]
        control_rows = [r for r in runs if r.arm == "control" and r.task == task]
        if not arm_rows or not control_rows:
            continue
        control_rate = Fraction(sum(r.correct for r in control_rows), len(control_rows))
        if not any(r.correct for r in arm_rows) and control_rate >= Fraction(1, 2):
            return True, f"task {task} incorrect in every run while control is correct in {control_rate}"
    return False, f"success {mine} vs control {control}"


def decide(runs: Sequence[TaskRun]) -> Decision:
    present = {r.arm for r in runs}
    if not set(_ARMS) <= present:
        return Decision("-", "not computed", f"needs all four arms, got {sorted(present)}")
    invalid = invalid_tasks(runs)
    if invalid:
        return Decision("validity", "invalid", f"no placeholder reached the model under (a) for: {', '.join(invalid)}")

    control = success(runs, "control")
    if control < Fraction(2, 3):
        return Decision("R0", "inconclusive", f"control success {control} < 2/3: re-run with a stronger model; (a) stays")

    a_fails, a_why = fails(runs, "a")
    if not a_fails:
        detail = f"(a) does not fail: {a_why}"
        if success(runs, "b") - success(runs, "a") >= Fraction(1, 3):
            detail += "; (b) scores >= 1/3 above (a): list it under Future Considerations"
        return Decision("R2", "a", detail)

    b_fails, b_why = fails(runs, "b")
    if not b_fails:
        return Decision("R3", "b", f"(a) fails ({a_why}); (b) does not ({b_why}): name a follow-up story")

    c_fails, c_why = fails(runs, "c")
    if not c_fails:
        return Decision(
            "R4",
            "c justified, not adopted",
            f"(a) fails ({a_why}); (b) fails ({b_why}); (c) does not ({c_why}): a stored mapping is PII at rest, "
            "so it goes to a later PRD; (a) stays",
        )
    return Decision("R5", "a", f"all three fail ((a) {a_why}; (b) {b_why}; (c) {c_why}): placeholders are not the bottleneck")


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def _version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _rate(value: Fraction) -> str:
    return f"{float(value):.2f}"


def report(runs: Sequence[TaskRun], header: dict) -> str:
    lines = ["# PRD-012 STORY-012: placeholder spike", ""]
    lines += [f"- {key}: {value}" for key, value in header.items()]
    lines.append("")

    lines += [
        "## Per arm and task",
        "",
        "| Arm | Task | Correct | Sent to model (max) | In model output | In artifact | Unresolved (c) | Replace misses | Parse errors | Mean turns | Aborts |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    arms = [arm for arm in _ARMS if any(r.arm == arm for r in runs)]
    tasks = [task for task in TASKS if any(r.task == task for r in runs)]
    for arm in arms:
        for task in tasks:
            rows = [r for r in runs if r.arm == arm and r.task == task]
            if not rows:
                continue
            aborts = sorted({r.aborted for r in rows if r.aborted})
            lines.append(
                f"| {arm} | {task} | {sum(r.correct for r in rows)}/{len(rows)} "
                f"| {max(r.sent for r in rows)} | {sum(r.in_output for r in rows)} "
                f"| {sum(r.in_artifact for r in rows)} | {sum(r.unresolved for r in rows)} "
                f"| {sum(r.replace_misses for r in rows)} | {sum(r.parse_errors for r in rows)} "
                f"| {sum(r.turns for r in rows) / len(rows):.1f} | {'; '.join(aborts) or '-'} |"
            )
    lines.append("")

    lines += ["## Per arm", "", "| Arm | Correct | Rate | Placeholders in model output |", "|---|---|---|---|"]
    for arm in arms:
        rows = [r for r in runs if r.arm == arm]
        lines.append(
            f"| {arm} | {sum(r.correct for r in rows)}/{len(rows)} | {_rate(success(runs, arm))} "
            f"| {sum(r.in_output for r in rows)} |"
        )
    lines.append("")

    lines += ["## Incorrect task-runs", ""]
    wrong = [r for r in runs if not r.correct]
    lines += [f"- {r.arm}/{r.task}/run {r.run}: {r.reason}" + (f" (aborted: {r.aborted})" if r.aborted else "") for r in wrong] or ["- none"]
    lines.append("")

    invalid = invalid_tasks(runs)
    if invalid:
        lines += [f"**INVALID**: no placeholder reached the model under (a) for: {', '.join(invalid)}", ""]

    decision = decide(runs)
    lines += ["## Decision", "", f"- rule: {decision.rule}", f"- outcome: **{decision.outcome}**", f"- detail: {decision.detail}"]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _guard_local(endpoint: str, allow_remote: bool) -> None:
    if allow_remote:
        return
    host = urlsplit(endpoint).hostname or ""
    if host in _LOCAL_HOSTS:
        return
    raise SystemExit(
        f"Refusing to write audit rows to a non-local database: {endpoint}\n"
        "Point --database-url at the local libSQL dev server, or pass "
        "--allow-remote-database if you are certain."
    )


def _guard_outside_repo(directory: Path) -> None:
    resolved = directory.resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise SystemExit(f"Refusing to write transcripts inside the repository: {resolved}")


def _choices(allowed: Sequence[str], label: str) -> Callable[[str], list[str]]:
    def parse(text: str) -> list[str]:
        values = [value.strip() for value in text.split(",") if value.strip()]
        unknown = [value for value in values if value not in allowed]
        if not values or unknown:
            raise argparse.ArgumentTypeError(f"{label} must be among {','.join(allowed)}, got {text!r}")
        return values

    return parse


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {text!r}")
    return value


def _measure_command(args: argparse.Namespace) -> int:
    _guard_local(_ENDPOINT, args.allow_remote_database)
    if args.transcripts is not None:
        _guard_outside_repo(args.transcripts)
    if (settings.OPENROUTER_API_KEY or "").strip() in _DUMMY_KEYS:
        print(
            "OPENROUTER_API_KEY is unset or a test dummy. This spike calls a real model: "
            "set OPENROUTER_API_KEY in the environment or .env and re-run.",
            file=sys.stderr,
        )
        return 1
    if not settings.PII_REDACTION_ENABLED:
        print("PII_REDACTION_ENABLED is false, so no arm masks anything. Set it true and re-run.", file=sys.stderr)
        return 1

    # Both lifespans' startup order (app/main.py).
    pii_redactor.load()
    authz.load()
    pattern_config.load()
    pii_policy.load()
    database.init_db()
    policy = get_pii_policy(_PROFILE)
    if not policy.structure_safe:
        print(f"profile {_PROFILE!r} resolved to a non-structure-safe policy ({policy.name}); nothing to compare.", file=sys.stderr)
        return 1

    params = GenerationParams(temperature=args.temperature, max_tokens=args.max_tokens)
    nonce = uuid.uuid4().hex[:8]
    started = datetime.now(timezone.utc)
    runs: list[TaskRun] = []
    for run in range(1, args.runs + 1):
        for task_id in args.tasks:
            for arm in args.arms:
                outcome = run_task(
                    TASKS[task_id], arm, run, model=args.model, nonce=nonce, max_turns=args.max_turns, params=params
                )
                runs.append(outcome)
                print(
                    f"  run {run} {task_id:<8} {arm:<8} correct={outcome.correct!s:<5} turns={outcome.turns} "
                    f"sent={outcome.sent} in_output={outcome.in_output} {outcome.aborted or ''}",
                    file=sys.stderr,
                    flush=True,
                )
                if args.transcripts is not None:
                    args.transcripts.mkdir(parents=True, exist_ok=True)
                    path = args.transcripts / f"{nonce}-{arm}-{task_id}-{run}.json"
                    path.write_text(json.dumps(outcome.transcript, indent=2), encoding="utf-8")

    header = {
        "model": args.model,
        "started": started.isoformat(timespec="seconds"),
        "runs": args.runs,
        "arms": ",".join(args.arms),
        "tasks": ",".join(args.tasks),
        "max turns": args.max_turns,
        "temperature": args.temperature,
        "max tokens": args.max_tokens,
        "code policy": f"entities={','.join(policy.entities)} threshold={policy.threshold} "
        f"skip_fenced_blocks={policy.skip_fenced_blocks} output={policy.output}",
        "presidio-analyzer": _version("presidio-analyzer"),
        "spacy": _version("spacy"),
        "python": platform.python_version(),
        "git": _git_sha(),
        "nonce": nonce,
    }
    print(report(runs, header))

    if args.json is not None:
        decision = decide(runs)
        payload = {
            "header": header,
            "decision": asdict(decision),
            "runs": [{k: v for k, v in asdict(r).items() if k != "transcript"} for r in runs],
        }
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\n  raw results written to {args.json}", file=sys.stderr)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare fixed, indexed and reversible PII placeholders on scripted agent "
            "tasks through run_conversation(profile='code') with a live model "
            "(PRD-012 STORY-012). Records outcomes; asserts none."
        )
    )
    parser.add_argument("--model", required=True, help="OpenRouter model slug; recorded in the report")
    parser.add_argument("--runs", type=_positive_int, default=3, help="repetitions of every task under every arm (default 3)")
    parser.add_argument("--arms", type=_choices(_ARMS, "arms"), default=list(_ARMS), help="default control,a,b,c")
    parser.add_argument("--tasks", type=_choices(tuple(TASKS), "tasks"), default=list(TASKS), help="default " + ",".join(TASKS))
    parser.add_argument("--max-turns", type=_positive_int, default=8, help="model turns per task-run (default 8)")
    parser.add_argument("--temperature", type=float, default=0.0, help="default 0.0")
    parser.add_argument("--max-tokens", type=_positive_int, default=4096, help="default 4096")
    parser.add_argument(
        "--database-url",
        default=_ENDPOINT,
        help="libSQL endpoint for the audit rows; read before argparse runs "
        "(default: $HARNESS_TEST_LIBSQL_URL or " + _DEFAULT_ENDPOINT + ")",
    )
    parser.add_argument("--allow-remote-database", action="store_true", help="write to a non-local DATABASE_URL (refused by default)")
    parser.add_argument("--json", type=Path, default=None, help="write raw per-task-run counts (no values, no transcripts) here")
    parser.add_argument("--transcripts", type=Path, default=None, help="dump raw per-task-run messages to this directory (outside the repo)")
    parser.set_defaults(func=_measure_command)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
