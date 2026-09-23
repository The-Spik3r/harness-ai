"""PRD-011 STORY-011: the false-positive corpus -- code and agent prompts under the built-in policy.

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
policy. STORY-012 appends the injection half to this module.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import re
import statistics
import time
from itertools import cycle
from pathlib import Path

import pytest

from app.config import settings
from app.models.messages import Message
from app.services.pattern_config import BUILT_IN_POLICY
from app.services.pattern_detector import PatternInspectionResult, inspect

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
