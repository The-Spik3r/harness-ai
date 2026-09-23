"""Pattern matching: the primitives and the conversation walk (PRD-011 Sections 6.2, 7/F1, F2, F5).

`compile_pattern` turns one configured pattern into one `re.Pattern`,
`has_nested_quantifier` is the startup-time ReDoS heuristic that guards the
`regex` mode (PRD-011 Section 9.2, T4), `strip_code_spans` implements the
`outside_code` scope, and `inspect()` walks a conversation under one profile's
role matrix. `pattern_config.py` compiles the policy at startup; the pipeline
calls `inspect()` at step 5 of `run_conversation`.

Pure on purpose: no I/O, no settings, no pydantic, no `app` import, nothing
read at import beyond a few compiled constants. Everything that reads
configuration -- the patterns file, `PATTERNS_ALLOW_REGEX`, the profiles, the
scan ceiling -- lives in `pattern_config.py` or is passed in by the caller.
`pattern_config.py` is also where `PatternCompileError` becomes a
`PatternConfigError` that can name the list a pattern came from (PRD-011
Section 6.9; the shape is `app/models/messages.py`).

The pre-PRD-011 substring detector and its seven-string constant were
**removed, not deprecated**, by STORY-008 (PRD-011 Section 10): a compatibility
shim would have been a second definition of "suspicious" for nobody's benefit.
`tests/test_pattern_characterization.py` keeps the verdicts it returned as a
frozen record, and asserts that exactly the enumerated ones changed.
"""

import re
from dataclasses import dataclass
from typing import Mapping, Optional, Protocol, Sequence


# --- PRD-011 STORY-002: compilation primitives -----------------------------


class PatternCompileError(Exception):
    """Raised by compile_pattern() when a pattern cannot become a regex:
    an empty or whitespace-only pattern, an unknown match mode, or a
    `regex` pattern the engine refuses.

    The message names the pattern and the underlying `re.error`, and nothing
    else. It deliberately does not name a list or a file: this module is pure
    and cannot know where the pattern came from. `pattern_config.load()`
    (STORY-005) catches this and re-raises `PatternConfigError` with the list
    name attached, which is the error an operator actually reads at startup."""


#: A quantified group whose body is itself quantified -- `(a+)+`, `(\w*)*`,
#: `(x+)*y`. Three alternatives: quantifier inside then `*`/`+` outside, an
#: open-ended `{n,}` inside, and an open-ended `{n,}` outside. Read textually
#: over the pattern source; see has_nested_quantifier() for the limits.
_NESTED_QUANTIFIER = re.compile(
    r"\([^()]*[+*][^()]*\)\s*[*+]"
    r"|\([^()]*\{\d+,\d*\}[^()]*\)\s*[*+]"
    r"|\([^()]*[+*][^()]*\)\s*\{\d+,\d*\}"
)


def compile_pattern(pattern: str, match: str) -> re.Pattern:
    """Compiles one pattern under `match`, always `re.IGNORECASE`.

    `word` is PRD-011 Section 6.2's formula: split the phrase on whitespace,
    `re.escape` each token, join the tokens with `\\s+`, wrap the whole in
    `\\b...\\b`. The per-token escape is what makes a pattern like `a.b` or
    `c+d` match literally; the `\\s+` join is what lets a multi-word phrase
    match across a line break or a doubled space. Escaping the phrase as one
    string instead would escape the spaces too and defeat that.

    `\\b` is a *word* boundary, not a whitespace boundary, so `override` does
    not match `overrides` but does match the `Override` in `@Override` -- `@`
    is a non-word character and therefore a boundary itself. PRD-011 Section
    6.2 is blunt about this: word matching does not fix `@Override`, and what
    does is the `code` profile not loading the keyword list at all.

    `regex` is the pattern as written. Whether a `regex` list is permitted at
    all is `PATTERNS_ALLOW_REGEX`, and whether this pattern is safe enough to
    accept is has_nested_quantifier() -- both are checked by the caller in
    `pattern_config` (STORY-005), because reading a setting here would cost
    this module its purity.

    Raises PatternCompileError for an empty or whitespace-only pattern, an
    unknown match mode, or a `regex` that does not compile."""
    if match == "word":
        tokens = pattern.split()
        if not tokens:
            raise PatternCompileError(
                f"word pattern {pattern!r} is empty or whitespace-only"
            )
        source = r"\b" + r"\s+".join(re.escape(token) for token in tokens) + r"\b"
        return re.compile(source, re.IGNORECASE)

    if match == "regex":
        if not pattern.strip():
            raise PatternCompileError(
                f"regex pattern {pattern!r} is empty or whitespace-only"
            )
        try:
            return re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise PatternCompileError(
                f"regex pattern {pattern!r} does not compile: {exc}"
            ) from exc

    raise PatternCompileError(
        f"unknown match mode {match!r} for pattern {pattern!r} "
        "(expected one of: word, regex)"
    )


def has_nested_quantifier(pattern: str) -> bool:
    """True when `pattern` has a quantified group whose body is itself
    quantified -- `(a+)+`, `(\\w*)*`, `(x+)*y` -- the shape that makes a regex
    backtrack catastrophically. `pattern_config` (STORY-005) refuses such a
    pattern at startup, which is PRD-011 Section 9.2 T4's third layer.

    **A heuristic for the common shape, not a proof of linear-time matching.**
    It reads the pattern as text and does not parse the regex grammar, so:

    - it does not see alternation-based blowup such as `(a|b)+`, which is a
      real catastrophic shape it returns False for;
    - it refuses escaped *literal* parentheses such as `\\(a\\+\\)+`, which are
      harmless.

    Both directions are deliberate. A false positive costs an operator one
    rewritten pattern at startup; a false negative costs a hung worker, so the
    check errs toward refusal. The real protection is that regex is off unless
    a deployment sets `PATTERNS_ALLOW_REGEX=true`, which is a deliberate act;
    nothing here should be read as a guarantee that an accepted pattern is
    safe."""
    return bool(_NESTED_QUANTIFIER.search(pattern))


# --- PRD-011 STORY-003: code-span stripping --------------------------------

#: An opening code fence: up to three leading spaces (CommonMark's tolerance
#: for an indented fence), then three or more backticks or tildes, then the
#: rest of the line. `re.MULTILINE` and not `re.DOTALL` because fence
#: detection is line-based -- `^` and `$` must mean line edges, and the span
#: is found by a second search rather than by one regex spanning both fences.
#: The trailing `[^\n]*` swallows the info string (```python), so the whole
#: opening line belongs to the span and the language name is stripped with it.
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})[^\n]*$", re.MULTILINE)

#: An inline code span: one, two or three backticks, a body, then the same run
#: again. `(?!\1)` on each body character is what lets ``a `b` c`` keep its
#: inner single backticks -- they are not the two-backtick delimiter, so the
#: body swallows them. `[^\n]` is what keeps a span inside one line, per
#: PRD-011 Section 6.5 ("inline spans -- single, double or triple backticks
#: within a line"). A lone unmatched backtick simply never matches.
_INLINE_SPAN = re.compile(r"(`{1,3})((?:(?!\1)[^\n])*)\1")


def _blank(text: str) -> str:
    """`text` with every non-newline character replaced by a newline: same
    length, same newline positions, no surviving words."""
    return re.sub(r"[^\n]", "\n", text)


def strip_code_spans(text: str) -> str:
    """`text` with fenced blocks and inline backtick spans blanked out, for a
    list carrying `scope: outside_code` (PRD-011 Section 6.5, F2).

    Two passes. Fences first: an opening fence is three or more backticks or
    tildes at the start of a line, and its closer is a run of the **same**
    character **at least as long**, alone on its line -- so ``` does not close
    a ~~~ block, and a ``` line inside a ````` block is content. An
    unterminated fence runs to the end of the text. Inline spans second, over
    the already-blanked text, which is why a backtick inside a fenced block
    can never open one.

    Blanking, not deleting: every non-newline character of the span becomes a
    newline, so `len(strip_code_spans(text)) == len(text)` and a match offset
    in the result still points at the same character of the original. It is
    also what stops the lines either side of a stripped block from fusing
    into one phrase. Note the converse, which is deliberate: because a blanked
    span is whitespace and a `word` pattern joins its tokens with `\\s+`, a
    phrase still matches *across* a stripped span. Wrapping the middle word of
    an injection phrase in backticks is therefore not an evasion.

    **A heuristic over markup, not a code parser.** Unfenced source gets no
    protection from it at all: a coding agent that pastes a bare file keeps
    every word in it, and a four-space-indented block -- CommonMark's other
    code construct -- is not recognised here and keeps its text too. This is
    exactly why the `code` profile's answer to `@Override` is not to rely on
    stripping but to not load the keyword list at all (PRD-011 Section 6.5);
    stripping is the second line, not the first. Read that sentence before
    concluding that a `tool` turn's code is safe from the keyword list.

    Lists carrying `scope: everywhere` are never passed through this function,
    which is how a fence is prevented from hiding an injection phrase
    (PRD-011 Section 9.2, T6).

    Its one caller is `inspect()` below, which computes at most two variants
    of a message's content -- raw and stripped -- and hands each list the one
    its scope asks for, so the stripping happens **once per message per scope
    requested, not once per pattern** (PRD-011 Section 7/F2 and Risk 8). That
    budget cannot be enforced from here: this function has no view of the
    message walk, so it is the caller's to keep, and `inspect()` keeps it."""
    out = []
    pos = 0
    while True:
        opening = _FENCE_OPEN.search(text, pos)
        if opening is None:
            out.append(text[pos:])
            break
        out.append(text[pos:opening.start()])
        delimiter = opening.group(1)
        closer = re.compile(
            r"^ {0,3}" + re.escape(delimiter[0]) + r"{%d,}[ \t]*$" % len(delimiter),
            re.MULTILINE,
        )
        closing = closer.search(text, opening.end())
        end = closing.end() if closing else len(text)
        out.append(_blank(text[opening.start():end]))
        pos = end

    # Second, and only now: a backtick inside a fenced block has already
    # become a newline, so it cannot open a span across unrelated text.
    return _INLINE_SPAN.sub(lambda span: _blank(span.group(0)), "".join(out))


# --- PRD-011 STORY-008: the conversation walk ------------------------------
#
# `inspect()` takes its inputs structurally. `pattern_config` imports this
# module, so importing `Profile` or `Message` back would be a cycle -- and this
# module imports nothing from `app` at all (the `app/models/messages.py` rule).
# The precedent is `DedupTurn` in `app/services/duplicate_checker.py`: a
# `Message`, a `PatternList` and a `Profile` satisfy these with no import in
# either direction.


class _Turn(Protocol):
    """One message: `app.models.messages.Message`, structurally."""

    role: str
    content: str


class _InspectedList(Protocol):
    """One list: `pattern_config.PatternList`, structurally."""

    name: str
    scope: str
    patterns: tuple[str, ...]
    compiled: tuple[re.Pattern, ...]


class _InspectedProfile(Protocol):
    """One profile: `pattern_config.Profile`, structurally."""

    lists: Sequence[_InspectedList]
    roles: Mapping[str, str]


@dataclass(frozen=True)
class PatternHit:
    """One match: which list and pattern, in which message, and what it does.

    `action` is `pattern_config.Action` -- `"block"` or `"flag"` -- typed
    `str` here because that alias cannot be imported without a cycle.
    """

    list_name: str
    pattern: str
    role: str
    message_index: int
    action: str


@dataclass(frozen=True)
class PatternInspectionResult:
    """What `inspect()` found (PRD-011 Section 7/F5).

    `block` is the first blocking hit, or None. `flags` is every flagging hit
    the walk passed before stopping, in walk order; the audit records only
    the first (PRD-011 Section 6.7). `truncated` is the index of every
    inspected message that was longer than the scan ceiling -- indices, not
    lengths or text, so the pipeline can warn about it without this result
    ever carrying content (PRD-011 Section 9.2, T9).
    """

    block: Optional[PatternHit] = None
    flags: tuple[PatternHit, ...] = ()
    truncated: tuple[int, ...] = ()


def inspect(
    messages: Sequence[_Turn],
    profile: _InspectedProfile,
    *,
    max_scan_characters: Optional[int] = None,
) -> PatternInspectionResult:
    """Walk `messages` under `profile`'s role matrix (PRD-011 Sections 6.4, 7/F5).

    The order is deterministic and is the reporting order: messages in order;
    within a message, the profile's lists in declared order; within a list,
    its patterns in declared order.

    **A message whose role is absent from `profile.roles` is not inspected**
    -- not scanned, not stripped, not truncated. That is the inspect-nothing
    default of PRD-011 Section 7/F4, the opposite of RBAC's deny-by-default.

    A hit takes its message's role action. `block` ends the walk at once and
    is returned with the flags gathered before it; `flag` is appended and the
    walk continues. Every hit is recorded, including several in one message.

    `max_scan_characters` bounds the text any one pattern runs over, and
    is passed in rather than read here because this module reads no settings.
    A longer message is cut **for matching only** -- the caller's message is
    untouched -- and its index lands in `truncated`. `None` means no ceiling.

    Code spans are stripped at most once per message, lazily, on the first
    list whose scope is `outside_code`; a list scoped `everywhere` always sees
    the raw text, so a fence cannot hide an injection phrase (T6).
    """
    flags: list[PatternHit] = []
    truncated: list[int] = []

    for index, message in enumerate(messages):
        action = profile.roles.get(message.role)
        if action is None:
            continue

        text = message.content
        if max_scan_characters is not None and len(text) > max_scan_characters:
            text = text[:max_scan_characters]
            truncated.append(index)

        stripped: Optional[str] = None
        for pattern_list in profile.lists:
            if pattern_list.scope == "outside_code":
                if stripped is None:
                    stripped = strip_code_spans(text)
                subject = stripped
            else:
                subject = text

            for pattern, compiled in zip(pattern_list.patterns, pattern_list.compiled):
                if not compiled.search(subject):
                    continue
                hit = PatternHit(
                    list_name=pattern_list.name,
                    pattern=pattern,
                    role=message.role,
                    message_index=index,
                    action=action,
                )
                if action == "block":
                    return PatternInspectionResult(
                        block=hit, flags=tuple(flags), truncated=tuple(truncated)
                    )
                flags.append(hit)

    return PatternInspectionResult(flags=tuple(flags), truncated=tuple(truncated))
