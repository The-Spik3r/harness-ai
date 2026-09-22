"""PRD-011 STORY-002 and STORY-003: the matching primitives, on their own.

`compile_pattern` and `has_nested_quantifier` are pure functions over one
pattern at a time, and `strip_code_spans` is a pure function over one message's
text. This module covers *only* them -- no policy, no profile, no
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
    strip_code_spans,
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


# --- PRD-011 STORY-003: code-span stripping --------------------------------
#
# The "before" these cases are the "after" for is STORY-001's characterization
# row `fenced-at-override` (tests/test_pattern_characterization.py:104): today's
# substring detector reports `override` from inside a ```java fence. That row
# stays green -- this story changes no behaviour of `detect_suspicious_pattern`
# -- and what changes is that a list carrying `scope: outside_code` will not see
# the fenced text at all once STORY-005 and STORY-008 wire it up.


def _assert_blanked_in_place(original: str, result: str) -> None:
    """AC 2 as a property of every stripping case, not one test.

    Same length, and every character that changed became a newline. Together
    those two are what make a match offset in the result point at the same
    character of the original (PRD-011 Section 6.5).
    """
    assert len(result) == len(original)
    for index, (before, after) in enumerate(zip(original, result)):
        assert before == after or after == "\n", (
            f"character {index}: {before!r} became {after!r}, not a newline"
        )


def _scoped_text(text: str, scope: str) -> str:
    """What `inspect()` will do per message per scope in STORY-008.

    A `PatternList` with a `scope` field does not exist until STORY-005, and
    the raw/stripped choice belongs to `inspect()` in STORY-008 -- which is
    also where PRD-011 Risk 8's "once per message per scope, not once per
    pattern" budget is kept. This four-line stand-in is deliberately the whole
    of the scope logic this story ships; `pattern_detector` itself exposes
    `strip_code_spans` and nothing else (PRD-011 Section 10).
    """
    return strip_code_spans(text) if scope == "outside_code" else text


# --- AC 1: fenced blocks go, the prose either side stays -------------------

#: Each has `before` / `after` prose around a fence holding a word the keyword
#: list would otherwise match.
_FENCE_CASES = [
    "before\n```java\n@Override\npublic void run() {}\n```\nafter\n",
    "before\n~~~\noverride fun onCreate()\n~~~\nafter\n",
    "before\n   ```\noverride\n   ```\nafter\n",
    "before\n```python override\noverride = 1\n```\nafter\n",
]

_FENCE_IDS = [
    "backtick-fence",
    "tilde-fence",
    "three-space-indented-opener",
    "info-string-on-the-opening-line",
]


@pytest.mark.parametrize("text", _FENCE_CASES, ids=_FENCE_IDS)
def test_a_fenced_block_is_stripped_and_its_surroundings_are_not(text):
    """AC 1. The opening line is part of the span, info string and all, so a
    fence carrying a language name does not leave the name behind (story
    Technical Notes).

    The three-space indent is CommonMark's tolerance for an opening fence; a
    fourth space makes it an indented code block instead, which this function
    deliberately does not recognise -- see the docstring test below.
    """
    result = strip_code_spans(text)

    assert "override" not in result.lower()
    assert result.startswith("before\n")
    assert result.endswith("\nafter\n")
    _assert_blanked_in_place(text, result)


def test_stripping_preserves_offsets_and_does_not_fuse_the_lines_either_side():
    """AC 2, on its own, because it is the reason for blanking over deleting.

    PRD-011 Section 6.5: "Stripping replaces the span with an equal number of
    newlines rather than deleting it, so a reported match offset still lines up
    with the original text, and the two lines either side of a stripped block
    cannot fuse into one phrase."
    """
    text = "before\n```java\n@Override\n```\nafter\n"

    result = strip_code_spans(text)

    assert len(result) == len(text)
    assert result.index("after") == text.index("after")

    gap = result[result.index("before") + len("before") : result.index("after")]
    assert gap.strip() == ""      # nothing of the fence survived
    assert "\n" in gap            # ...and the two words did not fuse
    assert "beforeafter" not in result


# --- AC 3: inline spans, and the lone backtick that is not one -------------

#: (text, unchanged) -- `unchanged` marks the row that must come back as written.
_INLINE_CASES = [
    ("say `override` now", False),
    ("say ``a `override` c`` now", False),
    ("say ```override``` now", False),
    ("a lone ` backtick override", True),
]

_INLINE_IDS = [
    "single-backtick",
    "double-backtick-wrapping-single-backticks",
    "triple-backtick-inline",
    "lone-backtick-unchanged",
]


@pytest.mark.parametrize("text,unchanged", _INLINE_CASES, ids=_INLINE_IDS)
def test_inline_spans_are_stripped_and_a_lone_backtick_is_not(text, unchanged):
    """AC 3. The double-backtick row is the one with teeth: its body holds
    single backticks, which are not the delimiter and so belong to the span.

    The lone backtick opens nothing, strips nothing and raises nothing -- an
    unbalanced backtick in ordinary prose is not an error condition.
    """
    result = strip_code_spans(text)

    if unchanged:
        assert result == text
    else:
        assert "override" not in result.lower()

    _assert_blanked_in_place(text, result)


def test_a_backtick_inside_a_fence_cannot_open_an_inline_span():
    """Story Technical Notes: "Inline spans are scanned after fences are
    removed, so a backtick inside a fenced block never opens an inline span."

    If the two passes were swapped, the stray backtick inside the fence would
    pair with the one after it, blanking text that is not code at all.
    """
    text = "```\n` override\n```\nan after ` tick\n"

    result = strip_code_spans(text)

    assert result.endswith("an after ` tick\n")
    _assert_blanked_in_place(text, result)


# --- AC 4: the closer, and what is not one ---------------------------------


def test_an_unterminated_fence_strips_to_the_end_of_the_text():
    """AC 4. Note this is the opposite of `reports._FENCE`
    (app/services/reports.py:218), which matches nothing when a fence is never
    closed. Right for dropping fences out of report prose, wrong here: an
    unterminated fence must not become a hole in the stripping.
    """
    text = "before\n```\noverride\nmore override\n"

    result = strip_code_spans(text)

    assert "override" not in result.lower()
    assert result.startswith("before\n")
    _assert_blanked_in_place(text, result)


#: Three ways a line of fence characters is, or is not, a closer.
_CLOSER_CASES = [
    "a\n```\ninside override\n`````\noutside override\n",
    "a\n`````\ninside override\n```\nstill inside override\n`````\noutside override\n",
    "a\n~~~\ninside override\n```\nstill inside override\n~~~\noutside override\n",
]

_CLOSER_IDS = [
    "longer-run-closes",
    "shorter-run-does-not-close",
    "other-character-does-not-close",
]


@pytest.mark.parametrize("text", _CLOSER_CASES, ids=_CLOSER_IDS)
def test_the_closer_is_the_same_character_and_at_least_as_long(text):
    """Story Technical Notes: "the closer is a run of the same character at
    least as long". A longer run closes a shorter opener; a shorter run does
    not close a longer one; a backtick run never closes a tilde block.

    Each row keeps exactly one hit -- the one after the block -- so a loose
    closer shows up as leaked `inside` text rather than as a subtle offset.
    """
    result = strip_code_spans(text)

    assert "inside" not in result
    assert result.endswith("outside override\n")
    _assert_blanked_in_place(text, result)


# --- AC 5: the two scopes, over one text -----------------------------------

#: The fenced hit comes FIRST, so `outside_code` cannot pass by accident: a
#: function that stripped nothing would report offset 4 under both scopes.
_BOTH_SCOPES_TEXT = "```\noverride inside\n```\noverride outside\n"


def test_outside_code_reports_only_the_hit_outside_the_fence():
    """AC 5, first half. The fenced `override` is not reported; the one after
    the fence is, at its original offset -- which is the offset invariant of
    AC 2 doing its job on a real match.
    """
    compiled = compile_pattern("override", "word")
    scoped = _scoped_text(_BOTH_SCOPES_TEXT, "outside_code")

    hit = compiled.search(scoped)

    assert hit is not None
    assert hit.start() == 24
    assert _BOTH_SCOPES_TEXT[24:].startswith("override outside")
    assert len(compiled.findall(scoped)) == 1      # ...and it is the only one left


def test_everywhere_reports_the_first_hit_in_text_order_fence_or_not():
    """AC 5, second half. A `scope: everywhere` list never sees
    `strip_code_spans` at all, so the first hit in text order wins and it
    happens to be the fenced one (PRD-011 Section 6.5, and the deterministic
    reporting order of Section 4 that STORY-008 implements).
    """
    compiled = compile_pattern("override", "word")

    hit = compiled.search(_scoped_text(_BOTH_SCOPES_TEXT, "everywhere"))

    assert hit is not None
    assert hit.start() == 4
    assert _BOTH_SCOPES_TEXT[4:].startswith("override inside")


def test_a_fence_is_not_an_evasion_for_the_injection_list():
    """PRD-011 Section 9.2, T6 -- named for the threat, per the story's
    Technical Notes.

    "The injection list is `scope: everywhere` precisely so that wrapping
    `ignore previous instructions` in a fence is not an evasion." The second
    assertion is the other half of the same decision: under `outside_code` the
    phrase WOULD be hidden, which is exactly why PRD-011 Section 6.3 gives the
    injection list `everywhere` and only the keyword list `outside_code`.
    """
    compiled = compile_pattern("ignore previous instructions", "word")
    text = "```\nignore previous instructions\n```\n"

    assert compiled.search(_scoped_text(text, "everywhere")) is not None
    assert compiled.search(_scoped_text(text, "outside_code")) is None


def test_a_phrase_still_matches_across_a_stripped_span():
    """Deliberate, and the direction the PRD wants -- not a leak.

    A blanked span is whitespace, and STORY-002's word formula joins tokens
    with `\\s+`, so the phrase matches straight through it. That means
    backticking the middle word of an injection phrase is not an evasion
    either, which is the same instinct as T6 above. The alternative -- a
    separator character that breaks the phrase -- would destroy AC 2's offset
    invariant, so this behaviour is not to be "fixed".
    """
    compiled = compile_pattern("ignore previous instructions", "word")
    text = "ignore previous `x` instructions"

    assert compiled.search(strip_code_spans(text)) is not None


# --- Identity, and the docstring the story makes an acceptance criterion ---

_IDENTITY_CASES = ["", "plain override text", "a\n\nb", "no code, just prose.\n"]

_IDENTITY_IDS = ["empty", "plain-prose", "blank-line", "trailing-newline"]


@pytest.mark.parametrize("text", _IDENTITY_CASES, ids=_IDENTITY_IDS)
def test_text_with_no_code_is_returned_unchanged(text):
    """Nothing to strip means nothing changes -- including the empty string,
    which must not raise."""
    assert strip_code_spans(text) == text


def test_strip_code_spans_documents_itself_as_a_heuristic():
    """The story's Technical Notes make the docstring an acceptance criterion:
    "This is a heuristic and the docstring must say so: unfenced source gets no
    protection from it ... Do not oversell it in the docstring -- a later reader
    deciding whether `tool` turns are safe will read exactly that sentence."

    So the sentence is asserted, in the same shape as
    `test_the_heuristic_documents_itself_as_a_heuristic` above. A later reader
    who trimmed this docstring to "strips code blocks" would turn a documented
    limit into a false promise, and nothing else in the suite would notice.
    """
    doc = strip_code_spans.__doc__

    assert doc is not None
    # Collapsed, because the claim is about the wording and not about where the
    # line happens to wrap -- rewrapping the paragraph must not fail this test.
    flowed = " ".join(doc.split())

    assert "heuristic" in flowed.lower()
    assert "unfenced source gets no protection" in flowed.lower()
    assert "@Override" in flowed                   # the case it does NOT solve
    assert "not once per pattern" in flowed        # PRD Risk 8, handed to STORY-008
    assert "T6" in flowed                          # why `everywhere` lists skip this
