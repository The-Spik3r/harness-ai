"""PRD-011 STORY-002: the compilation primitives, on their own.

`compile_pattern` and `has_nested_quantifier` are pure functions over one
pattern at a time. This module covers *only* them -- no policy, no profile, no
configuration file, no message walk -- because none of that exists yet:
`pattern_config.load()` arrives in STORY-005, the role matrix in STORY-006 and
`inspect(messages, profile)` in STORY-008. Anything asserted here about what a
deployment *matches in practice* would be asserting a policy this story does
not ship.

The pipeline still calls `detect_suspicious_pattern`, and
`tests/test_pattern_characterization.py` still pins its verdicts. Nothing in
this module touches either; the last test below exists to prove it.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import inspect
import re

import pytest

import app.services.pattern_detector as pattern_detector
from app.services.pattern_detector import (
    SUSPICIOUS_PATTERNS,
    PatternCompileError,
    compile_pattern,
    detect_suspicious_pattern,
    has_nested_quantifier,
)

# --- AC 1: `override` is a word, not a substring ---------------------------

#: (subject, matches) -- `override` compiled with match="word".
_OVERRIDE_CASES = [
    ("override", True),
    ("Override", True),
    ("OVERRIDE", True),
    ("please override the setting", True),
    ("overrides", False),
    ("overridden", False),
    ("overriding", False),
]

_OVERRIDE_IDS = [f"{subject}-{'match' if hit else 'clean'}" for subject, hit in _OVERRIDE_CASES]


@pytest.mark.parametrize("subject,expected", _OVERRIDE_CASES, ids=_OVERRIDE_IDS)
def test_word_match_is_case_insensitive_and_suffix_safe(subject, expected):
    """AC 1: the suffix family stops matching; case still does not matter.

    This is the whole point of PRD-011's move off the substring test (Section 4,
    "A word is not a substring"). Note that `overridden` and `overriding` were
    already clean *before* this PRD -- `override` is not a substring of either,
    the `e` is dropped -- so only `overrides` is a behaviour change here. See
    tests/test_pattern_characterization.py's module docstring, which corrects
    the PRD's claim to the contrary.
    """
    assert bool(compile_pattern("override", "word").search(subject)) is expected


def test_word_boundary_does_not_fix_at_override():
    """AC 1: `@Override` STILL matches, and that is not a defect to fix here.

    PRD-011 Section 6.2 is deliberately blunt about this: `@` is a non-word
    character and therefore itself a word boundary, so `\\boverride\\b` finds the
    `Override` in `@Override` exactly as the old substring test did. Word
    matching does not remove the single most common false positive in the brief.

    What removes it is the `code` profile not loading the `keywords` list at all
    (STORY-005/006), with `scope: outside_code` as the second line for profiles
    that do load it (STORY-003). Any later story written as though word
    boundaries solved `@Override` is written against a false premise -- this
    assertion is here so that premise cannot form.
    """
    assert compile_pattern("override", "word").search("@Override") is not None
    # The same reason, in the two other shapes the corpus will carry (STORY-011).
    assert compile_pattern("override", "word").search("public override void Draw()")
    assert compile_pattern("override", "word").search("override fun onCreate()")


# --- AC 2: multi-word phrases across whitespace ----------------------------

_PHRASE = "ignore previous instructions"

#: (subject, matches) -- the phrase compiled with match="word".
_PHRASE_CASES = [
    ("please ignore previous instructions now", True),
    ("ignore\nprevious  instructions", True),          # newline AND doubled space
    ("Ignore Previous Instructions", True),
    ("ignore\tprevious\ninstructions", True),
    ("ignoreprevious instructions", False),
    ("ignore previous", False),
]

_PHRASE_IDS = [
    "plain",
    "newline-and-doubled-space",
    "title-case",
    "tab-and-newline",
    "run-together",
    "partial-phrase",
]


@pytest.mark.parametrize("subject,expected", _PHRASE_CASES, ids=_PHRASE_IDS)
def test_phrase_matches_across_runs_of_whitespace(subject, expected):
    """AC 2: tokens are joined with `\\s+`, so any run of whitespace separates them.

    PRD-011 Section 6.2. `ignoreprevious instructions` does not match because
    `\\s+` requires at least one whitespace character between the tokens -- the
    phrase is three words, not a string with optional spaces.
    """
    assert bool(compile_pattern(_PHRASE, "word").search(subject)) is expected


# --- AC 3: metacharacters are literal in word mode -------------------------

#: (pattern, subject, matches) -- regex metacharacters must not be live.
_METACHARACTER_CASES = [
    ("a.b", "a.b", True),
    ("a.b", "axb", False),
    ("c+d", "c+d", True),
    ("c+d", "ccd", False),
    ("x*y", "x*y", True),
    ("x*y", "xxy", False),
]

_METACHARACTER_IDS = [
    "dot-literal",
    "dot-not-wildcard",
    "plus-literal",
    "plus-not-quantifier",
    "star-literal",
    "star-not-quantifier",
]


@pytest.mark.parametrize(
    "pattern,subject,expected", _METACHARACTER_CASES, ids=_METACHARACTER_IDS
)
def test_word_mode_escapes_metacharacters(pattern, subject, expected):
    """AC 3: each token is `re.escape`d BEFORE the tokens are joined with `\\s+`.

    The order matters and is the thing this test pins. Escaping the phrase as
    one string would escape its spaces too, and AC 2's newline case would fail
    while these still passed.
    """
    assert bool(compile_pattern(pattern, "word").search(subject)) is expected


def test_word_mode_rejects_an_empty_or_whitespace_only_pattern():
    """Story Technical Notes: an empty pattern must not compile to something
    that matches everywhere. `"".split()` is `[]`, which would otherwise build
    the bare `\\b\\b`."""
    with pytest.raises(PatternCompileError, match="empty or whitespace-only"):
        compile_pattern("", "word")

    with pytest.raises(PatternCompileError, match="empty or whitespace-only"):
        compile_pattern("   \n\t ", "word")


# --- AC 4: regex mode ------------------------------------------------------


def test_regex_mode_compiles_the_pattern_as_written_case_insensitively():
    """AC 4: the pattern is the author's, under `re.IGNORECASE`.

    `overrid\\w*` is PRD-011 threat T3's own example of what a deployment writes
    when it wants the stem back after word matching narrowed it.
    """
    compiled = compile_pattern(r"overrid\w*", "regex")

    assert compiled.flags & re.IGNORECASE
    assert compiled.search("overridden")
    assert compiled.search("OVERRIDING")
    assert compiled.search("override")


def test_regex_mode_raises_naming_the_pattern_and_the_re_error():
    """AC 4: both halves of the message are required.

    `pattern_config.load()` (STORY-005) catches this and re-raises with the list
    name attached; without the pattern text and the engine's own complaint, the
    operator's startup error would say only that *something* in some list failed.
    """
    with pytest.raises(PatternCompileError, match="does not compile") as excinfo:
        compile_pattern("(unclosed", "regex")

    message = str(excinfo.value)
    assert "(unclosed" in message                    # the pattern, named
    assert "missing )" in message or "unterminated" in message  # the re.error text


def test_regex_mode_rejects_an_empty_pattern():
    """The empty regex compiles happily and matches at every position, which is
    the `PATTERNS_ALLOW_REGEX` equivalent of the empty word pattern above."""
    with pytest.raises(PatternCompileError, match="empty or whitespace-only"):
        compile_pattern("", "regex")


def test_unknown_match_mode_raises_rather_than_returning_none():
    """Beyond the ACs, and deliberate (plan Risk R-3).

    PRD-011 Section 10 types the parameter `match: str`, not a `Literal`, so a
    typo reaches this function. STORY-005 validates `match` against the closed
    vocabulary at load, which should make this branch unreachable in production
    -- it exists so that an unreachable path fails loudly at startup instead of
    surfacing as a `NoneType has no attribute 'search'` at request time.
    """
    with pytest.raises(PatternCompileError, match="unknown match mode"):
        compile_pattern("override", "substring")


def test_regex_mode_does_not_consult_the_redos_heuristic():
    """The gate belongs to the caller, not the primitive (story Technical Notes).

    `compile_pattern` reads no setting and makes no policy decision, so a nested
    quantifier compiles here. Refusing it is `pattern_config.load()`'s job in
    STORY-005, because only the loader knows whether `PATTERNS_ALLOW_REGEX` is
    set and which list the pattern came from.
    """
    assert compile_pattern("(a+)+", "regex") is not None
    assert has_nested_quantifier("(a+)+") is True


# --- AC 5: the nested-quantifier heuristic ---------------------------------

#: (pattern, expected) -- the five AC 5 rows, plus two that document the edges.
_QUANTIFIER_CASES = [
    ("(a+)+", True),
    (r"(\w*)*", True),
    ("(x+)*y", True),
    (r"overrid\w*", False),
    (r"ignore\s+previous", False),
    ("(?:a+)+", True),
    ("(a{2,})+", True),
    ("(a+){2,}", True),
    ("ignore previous instructions", False),
    # A KNOWN LIMIT, NOT A BUG. `(a|b)+` is a real catastrophic-backtracking
    # shape and this heuristic returns False for it: the check looks for a
    # quantifier inside a quantified group, and alternation is not one. PRD-011
    # Section 9.2 T4 is written against exactly this -- the heuristic catches
    # "the common shape, not a proof of linear time", and the real protection is
    # that PATTERNS_ALLOW_REGEX is false by default. Do not "fix" this row
    # without also rewriting the docstring the test below enforces; a heuristic
    # that quietly claims more than it delivers is worse than one that is honest.
    ("(a|b)+", False),
    # The other edge, in the other direction: escaped LITERAL parentheses are
    # harmless and still refused, because the check reads the pattern as text
    # and does not parse the regex grammar. Erring toward refusal is deliberate
    # -- a false positive costs one rewritten pattern at startup, a false
    # negative costs a hung worker.
    (r"\(a\+\)+", True),
]

_QUANTIFIER_IDS = [
    "group-plus-plus",
    "group-star-star",
    "group-plus-star-suffix",
    "stem-regex-clean",
    "whitespace-regex-clean",
    "non-capturing-group",
    "counted-inside",
    "counted-outside",
    "plain-phrase-clean",
    "alternation-KNOWN-FALSE-NEGATIVE",
    "escaped-literal-parens-KNOWN-FALSE-POSITIVE",
]


@pytest.mark.parametrize("pattern,expected", _QUANTIFIER_CASES, ids=_QUANTIFIER_IDS)
def test_has_nested_quantifier(pattern, expected):
    """AC 5: True for the catastrophic shape, False for ordinary patterns."""
    assert has_nested_quantifier(pattern) is expected


def test_the_heuristic_documents_itself_as_a_heuristic():
    """AC 5 makes the docstring an acceptance criterion, so it is asserted.

    PRD-011 Section 9.2 T4 depends on this wording surviving: the heuristic is
    one of four layers and the weakest of them, and STORY-013's README work
    quotes this framing. A later reader who trims the docstring to "refuses
    catastrophic patterns" would turn a documented limit into a false promise,
    and nothing else in the suite would notice.
    """
    doc = has_nested_quantifier.__doc__

    assert doc is not None
    assert "heuristic" in doc.lower()
    assert "(a|b)+" in doc                      # the false negative, named
    assert "PATTERNS_ALLOW_REGEX" in doc        # what actually protects the deployment
    assert "proof" in doc.lower()               # ...and what this is not


# --- The module's purity, and the old API it must not disturb --------------


def test_pattern_detector_stays_a_pure_module():
    """PRD-011 Section 6.9: no settings, no file I/O, nothing read at import.

    The primitives are compiled here and the configuration that feeds them is
    read in `pattern_config.py` (STORY-005). That split is what lets this module
    be imported by a test with no environment and no database, and it is the one
    thing STORY-005 could break by accident -- by reaching for `settings` here
    rather than passing the value in.
    """
    source = inspect.getsource(pattern_detector)

    assert "settings" not in vars(pattern_detector)
    assert "open(" not in source
    assert "Path(" not in source
    # No import from the application package at all -- the messages.py rule.
    imports = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    assert not [line for line in imports if " app." in line or line.startswith("from app")]


def test_the_pre_prd_011_api_is_untouched_by_this_story():
    """Story Technical Notes: the pipeline still calls the old function, and
    STORY-001's characterization must stay green.

    STORY-008 deletes `detect_suspicious_pattern` and `SUSPICIOUS_PATTERNS`
    outright (PRD-011 Section 10: "removed, not deprecated"). It deletes this
    test with them, with a comment citing that decision -- until then, this is
    what holds STORY-002 to being purely additive.
    """
    assert SUSPICIOUS_PATTERNS[0] == "ignore previous instructions"
    assert len(SUSPICIOUS_PATTERNS) == 7

    result = detect_suspicious_pattern("please override now")

    assert result.is_suspicious is True
    assert result.pattern == "override"
    # Still the substring test it always was: the new word primitive did not
    # sneak into it. `overrides` is exactly the case that flips in STORY-008.
    assert detect_suspicious_pattern("it overrides the base").pattern == "override"
