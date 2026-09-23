"""PRD-011 STORY-011/012: the corpora -- code, agent prompts and injections under the built-in policy.

The "safe for code" claim of PRD-011 as evidence rather than assertion
(PRD-011 Sections 7/F8, 11 *Corpus criteria*). Every sample is a checked-in
file under `tests/corpora/`, discovered from disk: adding a sample needs no
edit here, and an empty directory fails the guard tests instead of
parametrizing to nothing (an empty parameter set is a skip, and a skip passes).

"Passes clean" means `inspect()` returns no block **and** no flag. Both are
asserted, separately, so a failure says which.

The profiles are `BUILT_IN_POLICY`'s, not `get_profile()`'s: the claim is
about the policy a deployment gets when it configures nothing, and `load()`
elsewhere in the suite can rebind the policy in force.

The `system`-turn cases cannot fail under the built-in `code` profile, which
does not inspect `system` at all (PRD-011 Section 6.4). They pin that
decision; the `user`-turn cases, scanned by the `scope: everywhere` injection
list, are the evidence.

Kept apart from `tests/test_pattern_characterization.py` on purpose: that
module records the *old* detector's verdicts, this one tests the *new*
policy.

STORY-012 adds the injection half, `tests/corpora/injections/`. Line 1 of
every sample is a header the test reads and strips before inspection:

    # expect: <block|flag> role: <user|tool>

A file without a valid header fails, so a case cannot be added without
stating what it should do, and adding one needs no edit here. Direct
injections are `user` turns, blocked under both built-in profiles; indirect
ones -- an instruction planted in a README, a CI log, a fetched page -- are
`tool` turns, flagged under `code` and not inspected under `chat`.

**The indirect cases document an accepted exposure, not a defence.** Under
`code` a `tool` hit is flagged and the conversation still reaches the model
(PRD-011 Section 9.2 T2, D4); the end-to-end tests below assert that it does,
planted text included. The enforcement point for what the model may then
*do* is PRD-015's action policy. A green suite here does not mean indirect
injection is handled. Promoting `tool` to `block` is a default change, not a
code change (PRD-011 Section 13): the action-parametrized tests already cover
both cells, so it needs a policy edit and the indirect headers, not a new test.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import re
import statistics
import time
from dataclasses import dataclass
from itertools import cycle
from pathlib import Path
from typing import Optional

import pytest

from app.config import settings
from app.models.messages import Message
from app.models.schemas import QueryBlockedSuspiciousResponse, QuerySuccessResponse
from app.services.pattern_config import BUILT_IN_POLICY
from app.services.pattern_detector import PatternInspectionResult, inspect, strip_code_spans
from tests.test_query_pipeline_patterns import (
    _Profile,
    _Upstream,
    _admit_tool_turns,
    _audit_rows_since,
    _fail_if_called,
    _indirect,
    _last_audit_id,
    _run,
    _use_profile,
)

_CORPORA = Path(__file__).resolve().parent / "corpora"

#: Metadata, not samples. Excluded by name so a new sample needs no test edit.
_NOT_SAMPLES = frozenset({"SOURCES.md"})

_CHAT = BUILT_IN_POLICY.profiles["chat"]
_CODE = BUILT_IN_POLICY.profiles["code"]

#: The PRD Risk 5 sample: the one verbatim prompt the built-in `chat` profile
#: blocks. See `tests/corpora/agent_prompts/SOURCES.md`.
_NON_VACUOUS_PROMPT = "codex-cli.md"


def _corpus(group: str) -> list[Path]:
    """Every sample in `tests/corpora/<group>/`, sorted, metadata excluded.

    A missing directory raises at collection, which is a loud failure.
    """
    return sorted(
        path
        for path in (_CORPORA / group).iterdir()
        if path.is_file() and path.name not in _NOT_SAMPLES and not path.name.startswith(".")
    )


def _read(path: Path) -> str:
    # No newline normalisation: the test sees the bytes a client would send.
    return path.read_text(encoding="utf-8")


def _describe(result: PatternInspectionResult) -> str:
    """The hits, never the content -- the prompts run to 26 KB."""
    hits = ([result.block] if result.block is not None else []) + list(result.flags)
    return ", ".join(f"{h.list_name}/{h.pattern!r}/{h.role}/#{h.message_index}" for h in hits)


_CODE_FILES = _corpus("code")
_PROMPT_FILES = _corpus("agent_prompts")


def _ids(paths: list[Path]) -> list[str]:
    return [path.name for path in paths]


# --- AC 4: discovery from disk; an empty corpus fails ---------------------

#: (suffix, what AC 1 requires of that file). A TypeScript `override` member is
#: a method, accessor or property -- not the word in a comment.
_REQUIRED_CODE_SAMPLES = (
    (".java", re.compile(r"@Override\b")),
    (".ts", re.compile(r"\boverride\s+(?:readonly\b|get\b|set\b|\w+\s*[(:=])")),
    (".cs", re.compile(r"\bpublic\s+override\b")),
    (".kt", re.compile(r"\boverride\s+fun\b")),
    (".css", re.compile(r"!important")),
)

#: Lines, not characters: "a plausible file, not a one-line stub" (AC 1).
_MIN_NON_BLANK_LINES = 30


def test_the_code_corpus_holds_the_five_required_samples():
    assert _CODE_FILES, "tests/corpora/code/ is empty"

    for suffix, construct in _REQUIRED_CODE_SAMPLES:
        matching = [p for p in _CODE_FILES if p.suffix == suffix and construct.search(_read(p))]
        assert matching, f"no {suffix} sample containing {construct.pattern!r}"

    css = [_read(p) for p in _CODE_FILES if p.suffix == ".css"]
    assert any(
        re.search(r"\boverride\b", comment)
        for text in css
        for comment in re.findall(r"/\*.*?\*/", text, re.DOTALL)
    ), "no .css sample with an override comment"

    for path in _CODE_FILES:
        lines = [line for line in _read(path).splitlines() if line.strip()]
        assert len(lines) >= _MIN_NON_BLANK_LINES, f"{path.name}: {len(lines)} lines, a stub"


def test_the_agent_prompt_corpus_holds_three_prompts_with_provenance():
    assert len(_PROMPT_FILES) >= 3, f"{len(_PROMPT_FILES)} agent prompts, need 3"

    sources = _CORPORA / "agent_prompts" / "SOURCES.md"
    assert sources.is_file(), "tests/corpora/agent_prompts/SOURCES.md is missing"
    provenance = _read(sources)
    for path in _PROMPT_FILES:
        assert f"`{path.name}`" in provenance, f"{path.name} has no provenance in SOURCES.md"

    assert _NON_VACUOUS_PROMPT in _ids(_PROMPT_FILES)


# --- AC 1: every code sample passes clean under `code`, as a user turn ------


@pytest.mark.parametrize("path", _CODE_FILES, ids=_ids(_CODE_FILES))
def test_code_sample_passes_clean_under_code_as_a_user_turn(path):
    result = inspect([Message("user", _read(path))], _CODE)

    assert result.block is None, f"{path.name}: blocked by {_describe(result)}"
    assert result.flags == (), f"{path.name}: flagged by {_describe(result)}"


# --- AC 2: every agent prompt passes clean under `code`, as system and user --


# The `system` cases cannot fail while the built-in `code` profile leaves
# `system` uninspected (PRD-011 Section 6.4). They pin that decision. The
# `user` cases are the evidence.
@pytest.mark.parametrize("role", ["system", "user"])
@pytest.mark.parametrize("path", _PROMPT_FILES, ids=_ids(_PROMPT_FILES))
def test_agent_prompt_passes_clean_under_code(path, role):
    result = inspect([Message(role, _read(path))], _CODE)

    assert result.block is None, f"{path.name} as {role}: blocked by {_describe(result)}"
    assert result.flags == (), f"{path.name} as {role}: flagged by {_describe(result)}"


# --- AC 3: the corpus is not vacuous (PRD-011 Risk 5) ----------------------


def test_an_agent_prompt_is_blocked_by_the_built_in_chat_profile():
    """The proof the corpus is not vacuous (PRD-011 Section 14, Risk 5).

    The Codex CLI system prompt passes clean under `code` (above), and the
    built-in `chat` profile -- the policy every request got before PRD-011 --
    blocks it. The catch is `override`, from the prose line "user instructions
    (i.e. AGENTS.md) may override these guidelines". So the `code` profile
    changes a real verdict on a real prompt; the sample was not chosen because
    it happens to pass.
    """
    result = inspect([Message("user", _read(_CORPORA / "agent_prompts" / _NON_VACUOUS_PROMPT))], _CHAT)

    assert result.block is not None
    assert (result.block.list_name, result.block.pattern, result.block.role) == (
        "keywords",
        "override",
        "user",
    )


def _carries_a_required_construct(path: Path) -> bool:
    text = _read(path)
    return any(path.suffix == suffix and construct.search(text) for suffix, construct in _REQUIRED_CODE_SAMPLES)


#: The AC 1 samples. Only these are held to the companion test below: a sample
#: an operator adds later -- clean Go, say -- need not contain `override`.
_OVERRIDE_SAMPLES = [path for path in _CODE_FILES if _carries_a_required_construct(path)]


# The same Risk 5 argument for the code half. `@Override` is a word-boundary
# match (PRD-011 Section 6.2), so word matching alone would not have passed
# this corpus: the `code` profile not loading `keywords` does.
@pytest.mark.parametrize("path", _OVERRIDE_SAMPLES, ids=_ids(_OVERRIDE_SAMPLES))
def test_code_sample_is_blocked_by_the_built_in_chat_profile(path):
    result = inspect([Message("user", _read(path))], _CHAT)

    assert result.block is not None, f"{path.name}: passes `chat` too, so proves nothing"
    assert result.block.list_name == "keywords", f"{path.name}: {_describe(result)}"


# --- AC 5: inspection cost at the CONTEXT_MAX_MESSAGES ceiling -------------

_TIMED_RUNS = 25


def test_inspection_cost_at_the_context_max_messages_ceiling(record_property):
    """Measured and printed for the story report -- **no threshold asserted**.

    PRD-011 Section 11 asks for a number in the report, not a CI gate; a
    wall-clock assertion is exactly what `test_query_router.py:311-318` shows
    to avoid on shared runners. The conversation is the largest the pipeline's
    step 3 admits: `CONTEXT_MAX_MESSAGES` messages sharing
    `CONTEXT_MAX_CHARACTERS`, every one of them inspected under `code`
    (alternating `user` and `tool`), and none of them a hit, so the walk runs
    to the end without a short-circuit. Called the way the pipeline calls it.
    """
    count = settings.CONTEXT_MAX_MESSAGES
    share = settings.CONTEXT_MAX_CHARACTERS // count
    texts = cycle(_read(path)[:share] for path in _CODE_FILES + _PROMPT_FILES)
    roles = cycle(("user", "tool"))
    messages = [Message(next(roles), next(texts)) for _ in range(count)]
    total_characters = sum(len(message.content) for message in messages)

    def run() -> PatternInspectionResult:
        return inspect(messages, _CODE, max_scan_characters=settings.PATTERN_MAX_SCAN_CHARACTERS)

    result = run()  # warm-up, and the shape check below
    timings_ms = []
    for _ in range(_TIMED_RUNS):
        start = time.perf_counter()
        run()
        timings_ms.append((time.perf_counter() - start) * 1000)

    assert len(messages) == count
    assert total_characters <= settings.CONTEXT_MAX_CHARACTERS
    assert result.block is None and result.flags == (), _describe(result)

    median = statistics.median(timings_ms)
    record_property("inspect_ceiling_median_ms", round(median, 3))
    print(
        f"\nSTORY-011 ceiling: {count} messages, {total_characters} chars, code profile, "
        f"{_TIMED_RUNS} runs: min {min(timings_ms):.3f} ms / median {median:.3f} ms / "
        f"max {max(timings_ms):.3f} ms"
    )


# ===========================================================================
# PRD-011 STORY-012: the injection corpus.
# ===========================================================================

#: Line 1 of every injection sample. Closed vocabulary: anything else fails
#: that file's header test -- a case cannot be added without a verdict. The
#: trailing `\s*` absorbs the `\r` of a CRLF checkout.
_HEADER = re.compile(r"^# expect: (?P<expect>block|flag) role: (?P<role>user|tool)\s*$")

_HEADER_FORMAT = "# expect: <block|flag> role: <user|tool>"


@dataclass(frozen=True)
class _Case:
    """One injection sample: its declared verdict and role, and the body a client would send."""

    path: Path
    expect: str
    role: str
    body: str


def _case(path: Path) -> Optional[_Case]:
    """The header, parsed and stripped; None when line 1 is not a valid header."""
    first, _, body = _read(path).partition("\n")
    match = _HEADER.match(first)
    return _Case(path, match["expect"], match["role"], body) if match else None


def _case_ids(cases: list[_Case]) -> list[str]:
    return [case.path.name for case in cases]


_INJECTION_FILES = _corpus("injections")
_INJECTION_CASES = [case for case in map(_case, _INJECTION_FILES) if case is not None]
_DIRECT = [case for case in _INJECTION_CASES if case.role == "user"]
_INDIRECT = [case for case in _INJECTION_CASES if case.role == "tool"]
_INJECTION_LIST = BUILT_IN_POLICY.lists["injection"]


def _injection_hit(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INJECTION_LIST.compiled)


#: Direct cases whose every injection phrase sits inside a code span: a hit
#: on the raw body and none once the spans are stripped (AC 5, T6).
_FENCED = [case for case in _DIRECT if _injection_hit(case.body) and not _injection_hit(strip_code_spans(case.body))]


# --- AC 3: every sample declares its verdict; the corpus is populated ------


# Parametrized over the *files*, not the parsed cases: a bad header must fail
# here, not drop silently out of every other parameter set.
@pytest.mark.parametrize("path", _INJECTION_FILES, ids=_ids(_INJECTION_FILES))
def test_every_injection_sample_declares_its_verdict(path):
    first = _read(path).partition("\n")[0]

    assert _case(path) is not None, f"{path.name}: line 1 is not {_HEADER_FORMAT!r} (got {first[:80]!r})"


def test_the_injection_corpus_holds_five_direct_and_two_indirect_cases():
    assert _INJECTION_FILES, "tests/corpora/injections/ is empty"

    # The two cells the AC names. Any other pairing -- a `flag` on a `user`
    # turn, a `block` on a `tool` turn -- is not a case this corpus knows.
    for case in _DIRECT:
        assert case.expect == "block", f"{case.path.name}: a user-turn case must expect block"
    for case in _INDIRECT:
        assert case.expect == "flag", f"{case.path.name}: a tool-turn case must expect flag"

    assert len(_DIRECT) >= 5, f"{len(_DIRECT)} direct injections, need 5"
    assert len(_INDIRECT) >= 2, f"{len(_INDIRECT)} indirect injections, need 2"


def test_the_direct_cases_cover_every_injection_phrase():
    """Only `injection` is loaded by `code`, so only its phrases can block a
    direct case under both profiles. Each is exercised by at least one case;
    read from the policy, so the guard grows with the list."""
    caught = set()
    for case in _DIRECT:
        result = inspect([Message("user", case.body)], _CODE)
        if result.block is not None:
            caught.add(result.block.pattern)

    missing = [pattern for pattern in _INJECTION_LIST.patterns if pattern not in caught]
    assert not missing, f"no direct case is blocked by: {missing}"


def test_the_corpus_holds_a_fenced_injection():
    """AC 5: one case covers the fence evasion explicitly -- its phrase lives
    only inside a code span, so it is the evasion and not a phrase that happens
    to sit next to a fence."""
    assert _FENCED, "no direct case has its injection phrase inside a code fence only"


# --- AC 1: every direct injection is blocked under both profiles -----------


@pytest.mark.parametrize("profile", [_CHAT, _CODE], ids=["chat", "code"])
@pytest.mark.parametrize("case", _DIRECT, ids=_case_ids(_DIRECT))
def test_direct_injection_is_blocked(case, profile):
    result = inspect([Message(case.role, case.body)], profile)

    assert result.block is not None, f"{case.path.name}: not blocked ({_describe(result)})"
    assert (result.block.list_name, result.block.role, result.block.action) == (
        "injection",
        "user",
        case.expect,
    ), f"{case.path.name}: {_describe(result)}"


# --- AC 5: the fence does not hide an injection (PRD-011 Section 9.2, T6) ---


# Overlaps AC 1 on purpose: the AC asks for the evasion to be covered
# explicitly, so a failure here names it. `injection` is `scope: everywhere`
# and is never stripped; only `keywords` is `outside_code`.
@pytest.mark.parametrize("profile", [_CHAT, _CODE], ids=["chat", "code"])
@pytest.mark.parametrize("case", _FENCED, ids=_case_ids(_FENCED))
def test_a_fenced_injection_is_caught(case, profile):
    result = inspect([Message(case.role, case.body)], profile)

    assert result.block is not None, f"{case.path.name}: the fence hid it ({_describe(result)})"
    assert result.block.list_name == "injection"


# --- AC 2: every indirect injection is flagged under `code`, not inspected under `chat`


@pytest.mark.parametrize("case", _INDIRECT, ids=_case_ids(_INDIRECT))
def test_indirect_injection_is_flagged_under_code(case):
    result = inspect([Message(case.role, case.body)], _CODE)

    # A flag that blocked would be the worse failure: the agent's session dies
    # on a file it read (PRD-011 D4).
    assert result.block is None, f"{case.path.name}: blocked by {_describe(result)}"
    assert result.flags, f"{case.path.name}: not flagged"
    first = result.flags[0]
    assert (first.list_name, first.role, first.action) == ("injection", "tool", case.expect), _describe(result)


@pytest.mark.parametrize("case", _INDIRECT, ids=_case_ids(_INDIRECT))
def test_indirect_injection_is_not_inspected_under_chat(case):
    result = inspect([Message(case.role, case.body)], _CHAT)

    assert result.block is None, f"{case.path.name}: blocked by {_describe(result)}"
    assert result.flags == (), f"{case.path.name}: flagged by {_describe(result)}"

    # An empty result looks the same whether the turn was skipped or the text
    # stopped matching. The same body as a `user` turn under the same profile
    # is blocked by `injection`, so the empty result above is the role cell.
    as_user = inspect([Message("user", case.body)], _CHAT)
    assert as_user.block is not None and as_user.block.list_name == "injection", (
        f"{case.path.name}: no injection hit even as a user turn ({_describe(as_user)})"
    )


# --- Promotion of `tool` is a policy edit, not a new test (PRD-011 Section 13)


def _code_with_tool(action: str) -> _Profile:
    """The built-in `code` profile with only the tool cell set: promotion is exactly this."""
    return _Profile(lists=_CODE.lists, roles={**_CODE.roles, "tool": action})


# When the default is promoted, the edits are the built-in `code` profile and
# each indirect file's header. This test already covers both cells.
@pytest.mark.parametrize("action", ["flag", "block"])
@pytest.mark.parametrize("case", _INDIRECT, ids=_case_ids(_INDIRECT))
def test_indirect_injection_follows_the_tool_cell(case, action):
    result = inspect([Message("tool", case.body)], _code_with_tool(action))

    if action == "block":
        hit = result.block
    else:
        assert result.block is None, f"{case.path.name}: blocked by {_describe(result)}"
        hit = result.flags[0] if result.flags else None
    assert hit is not None, f"{case.path.name}: no {action}"
    assert (hit.list_name, hit.role, hit.action) == ("injection", "tool", action), _describe(result)


# --- AC 4: a flagged indirect injection writes its row AND reaches the model


def _reached_the_model(pattern: str, sent: list) -> bool:
    """The planted phrase is in a `tool` turn upstream received -- whitespace
    and case tolerant, the way the `word` match itself is."""
    phrase = re.compile(r"\s+".join(map(re.escape, pattern.split())), re.IGNORECASE)
    return any(message.role == "tool" and phrase.search(message.content) for message in sent)


def _assert_flagged_and_answered(result, upstream: _Upstream, rows: list) -> None:
    assert isinstance(result, QuerySuccessResponse), f"not answered: {result!r}"
    assert len(upstream.calls) == 1, "the model was not called"

    assert len(rows) == 2, [(row.pattern_role, row.pattern_action) for row in rows]
    flag, success = rows
    assert (flag.pattern_role, flag.pattern_action) == ("tool", "flag")
    assert flag.suspicious_pattern in _INJECTION_LIST.patterns
    assert flag.success is True
    assert flag.response_preview is None
    assert success.pattern_action is None
    assert success.response_preview == "Hi there!"
    assert result.audit_id == success.id

    # T2, literally: the planted instruction is in what the model was sent.
    assert _reached_the_model(flag.suspicious_pattern, upstream.calls[0])


@pytest.mark.parametrize("case", _INDIRECT, ids=_case_ids(_INDIRECT))
def test_indirect_injection_flags_and_still_calls_the_model(case, temp_db, monkeypatch):
    """PRD-011 T2, D4: the accepted exposure, asserted. Both halves -- the
    flag row and the upstream call -- because a "flag" that quietly blocked
    would be the worse failure. `_admit_tool_turns` is the STORY-009 seam:
    step 0 and dedup_key refuse `tool` turns until PRD-016."""
    _admit_tool_turns(monkeypatch)
    upstream = _Upstream()
    before = _last_audit_id()

    result = _run(_indirect(case.body), call_openrouter=upstream, profile="code")

    _assert_flagged_and_answered(result, upstream, _audit_rows_since(before))


#: One case end to end per action: each test costs a database reset.
_PROMOTED = _INDIRECT[:1]


@pytest.mark.parametrize("action", ["flag", "block"])
@pytest.mark.parametrize("case", _PROMOTED, ids=_case_ids(_PROMOTED))
def test_indirect_injection_end_to_end_follows_the_tool_cell(case, action, temp_db, monkeypatch):
    """The same arm with the tool cell set to each action: a promoted cell
    blocks with no upstream call, an unpromoted one answers."""
    _admit_tool_turns(monkeypatch)
    _use_profile(monkeypatch, _code_with_tool(action))
    upstream = _Upstream() if action == "flag" else _fail_if_called
    before = _last_audit_id()

    result = _run(_indirect(case.body), call_openrouter=upstream, profile="code")
    rows = _audit_rows_since(before)

    if action == "flag":
        _assert_flagged_and_answered(result, upstream, rows)
    else:
        assert isinstance(result, QueryBlockedSuspiciousResponse)
        assert len(rows) == 1
        assert (rows[0].pattern_role, rows[0].pattern_action) == ("tool", "block")
        assert rows[0].suspicious_pattern == result.pattern
