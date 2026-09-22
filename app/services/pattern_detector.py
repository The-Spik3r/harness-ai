"""Pattern matching primitives (PRD-011 Sections 6.2 and 7/F1).

`compile_pattern` turns one configured pattern into one `re.Pattern`, and
`has_nested_quantifier` is the startup-time ReDoS heuristic that guards the
`regex` mode (PRD-011 Section 9.2, T4). Neither has a caller yet: the policy
that compiles patterns arrives with `pattern_config.py` (STORY-005) and the
conversation walk with `inspect()` (STORY-008).

Pure on purpose: no I/O, no settings, no pydantic, no `app` import, nothing
read at import beyond one compiled constant. Everything that reads
configuration -- the patterns file, `PATTERNS_ALLOW_REGEX`, the profiles --
lives in `pattern_config.py`, which is also where `PatternCompileError`
becomes a `PatternConfigError` that can name the list a pattern came from
(PRD-011 Section 6.9; the shape is `app/models/messages.py`).

`SUSPICIOUS_PATTERNS` and `detect_suspicious_pattern` below are pre-PRD-011
and still the pipeline's only pattern check. STORY-008 removes them; until
then they are untouched, and `tests/test_pattern_characterization.py` pins
every verdict they return.
"""

import re
from dataclasses import dataclass
from typing import List, Optional

SUSPICIOUS_PATTERNS: List[str] = [
    "ignore previous instructions",
    "forget everything",
    "show system prompt",
    "reveal password",
    "execute code",
    "admin mode",
    "override",
]


@dataclass
class PatternDetectionResult:
    is_suspicious: bool
    pattern: Optional[str] = None


def detect_suspicious_pattern(prompt: str) -> PatternDetectionResult:
    lowered = prompt.lower()
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern in lowered:
            return PatternDetectionResult(is_suspicious=True, pattern=pattern)
    return PatternDetectionResult(is_suspicious=False)


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
