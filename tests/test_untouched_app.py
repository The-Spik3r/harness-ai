"""PRD-006's containment, asserted against git rather than remembered.

STORY-020's job was to prove that the admin console lives entirely inside
`chat_ui/` — no new route, no new query, no schema migration, no new dependency,
and no change to the chat PRD-004 shipped. That proof was a document, and a
document does not fail when someone adds a database function next month. This
file is the same proof, re-run on every suite.

**Why the provenance guards were retired (PRD-008 STORY-023).**
Four guards here once asserted "this path has not changed since `_BASE`" by
diffing the pinned baseline against the **working tree**. That comparison
answers "what changed since PRD-006 began"; it never answered "what did PRD-006
change". The two are the same question only while PRD-006 is the last thing on
the branch, and they stopped being the same at `0f77203` ("Merge branch 'main'
into epic/PRD-006-admin-console"), which pulled PRD-005's work under `app/` into
the diff range. The guards were therefore already unmeasurable before PRD-007
existed; PRD-007 and PRD-008 only widened a gap that was already open. By
PRD-008 they reported fifteen files under `app/`, a requirements file and six
chat modules, none of it PRD-006's doing, and took CI down with them.

**The claim itself was true; only the instrument was broken.** The 40 commits
from `577a285` (STORY-001) to `99afc9f` (STORY-020) touched zero files under
`app/`, zero lines of either requirements file, neither `Caddyfile` nor
`rxconfig.py`, none of the six chat modules and none of the six pinned suites —
the only `components/` files they added are the console's own `admin_shell.py`,
`register.py` and `summary.py`. `git diff --name-only d3e6279 99afc9f -- app/`
is empty, and stays empty forever. That is exactly why the assertion is gone
rather than repaired: pinned between two immutable commits it could never fail
again, and a test that can only pass is not a test. The evidence is preserved as
a finding in STORY-023's report, which is where a settled historical fact
belongs.

`_BASE` is deliberately **not** re-baselined to a newer commit. Doing so would
turn the suite green today and break it again at the next PRD, which is the
cycle STORY-023 exists to end.

What survives is what is still falsifiable: that no test disappeared from the
suites PRD-006 promised to leave alone, that no shared theme token was retuned,
and that the chat's own relative-time wording still renders what PRD-004
shipped. Each compares *values or names* rather than file bytes, because that is
the claim that actually matters — the argument
`test_no_theme_token_was_retuned_or_removed` already made for itself, now
applied to the whole module.

The guards skip rather than fail when git or the history is unavailable — a
shallow clone or an exported tree should not turn a provenance check into a red
suite. That concession is inherited from the PRD-003 guard deliberately, and it
is load-bearing in CI, where `actions/checkout@v4` fetches depth 1 and `_BASE`
does not resolve at all.
"""

import ast
import pathlib
import re
import subprocess

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# PRD-006's baseline: the parent of 577a285 (STORY-001, this PRD's first
# commit), i.e. the tree as it stood the moment before the console existed.
# Everything below asks "what did PRD-006 change", never "what does this branch
# contain".
_BASE = "d3e6279"

# PRD-006 Section 15, "Tests that must pass unmodified". These six were once
# pinned byte-for-byte; STORY-023 asserts them by census instead, for the reason
# the module docstring gives. Extending one of them passes, deleting a case from
# one fails.
_UNMODIFIED_SUITES = (
    "tests/test_admin_auth.py",
    "tests/test_audit_router.py",
    "tests/test_stats_router.py",
    "tests/test_db.py",
    "tests/test_route_reservations.py",
    "tests/test_chat_state.py",
)

# The two suites PRD-006's own stories were allowed to extend. Now that both
# lists are asserted by census, the two could collapse into one -- they stay
# separate because `test_no_assertion_was_removed_from_the_two_extendable_suites`
# reads this name, and STORY-023 requires that guard to stay byte-unmodified.
# The distinction they record is also still real: these two were expected to
# grow, the six above were expected never to be opened at all.
_EXTENDED_SUITES = ("tests/test_copy.py", "tests/test_contrast.py")

_TEST_DEF = re.compile(r"^def (test_\w+)", re.MULTILINE)

# Test functions removed from a pinned suite on purpose, by a later PRD that
# reached this branch through `main` -- not by PRD-006, and not by accident.
#
# `a38f38b` is PRD-005 STORY-014, "chat UI login replaces the free-text user_id
# prompt": `ChatState.submit_user_id()`/`reset_user_id()` became
# `login()`/`logout()`, so the tests whose entire premise was the free-text
# prompt had nothing left to assert. Each was replaced in the same file:
#   - test_chat_state_submit_empty_or_whitespace_user_id_shows_error ->
#     test_chat_state_login_empty_token_shows_error
#   - test_chat_state_submit_valid_user_id_clears_error_and_sets_user ->
#     test_chat_state_login_valid_token_sets_user_id_and_clears_error
#   - test_chat_state_reset_user_id_clears_error -> folded into
#     test_chat_state_logout_clears_session_and_credential
#   - test_reset_user_id_clears_the_transcript -> test_logout_clears_the_transcript
#
# `tests/test_pii_redaction_integration.py` carries the identical allowlist, for
# the identical four names and the identical reason, in
# `_DELIBERATELY_SUPERSEDED_TESTS`. This is that mechanism, not a new one.
_DELIBERATELY_SUPERSEDED_TESTS = {
    "tests/test_chat_state.py": {
        "test_chat_state_submit_empty_or_whitespace_user_id_shows_error",
        "test_chat_state_submit_valid_user_id_clears_error_and_sets_user",
        "test_chat_state_reset_user_id_clears_error",
        "test_reset_user_id_clears_the_transcript",
    },
}


def _git(*args):
    """Run a git command at the repo root; None when git/history is unavailable."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _base():
    """The pinned baseline, or None when this tree cannot resolve it."""
    resolved = _git("rev-parse", "--verify", f"{_BASE}^{{commit}}")
    return resolved.strip() if resolved and resolved.strip() else None


@pytest.mark.parametrize("path", _UNMODIFIED_SUITES)
def test_no_test_was_removed_from_the_six_pinned_suites(path):
    """AC 1: the six suites PRD-006 promised never to open, asserted by census.

    Byte-equality was the wrong instrument for the same reason it was wrong for
    `theme.py`: it fires on any edit, including the ones that add coverage.
    Four of these six have since been extended -- `test_db.py` alone went from
    23 test functions to 118 -- and every one of those additions would have to
    be argued with a guard that only knows about bytes, which is how a guard
    becomes decoration and then gets deleted.

    What is worth protecting is the coverage, so that is what is asserted:
    every test function present at the baseline is still present by name.
    Extending a suite passes. Deleting a case fails.
    """
    base = _base()
    if base is None:
        pytest.skip(f"baseline {_BASE} not resolvable; provenance unverifiable here")

    base_source = _git("show", f"{base}:{path}")
    assert base_source is not None, f"git show failed for {path}"
    current = _REPO_ROOT / path
    current_source = current.read_text(encoding="utf-8") if current.exists() else ""

    gone = set(_TEST_DEF.findall(base_source)) - set(_TEST_DEF.findall(current_source))
    gone -= _DELIBERATELY_SUPERSEDED_TESTS.get(path, set())

    assert sorted(gone) == [], f"{path} lost test functions present at {_BASE}: {sorted(gone)}"


def test_no_assertion_was_removed_from_the_two_extendable_suites():
    """AC 1, the half byte-equality cannot cover.

    `test_copy.py` and `test_contrast.py` were extended by this PRD's own
    stories, so a diff against them is expected and says nothing. What must
    still hold is that extending them never *removed* a check: every test
    function present at the baseline is still present by name.
    """
    base = _base()
    if base is None:
        pytest.skip(f"baseline {_BASE} not resolvable; provenance unverifiable here")

    missing = {}
    for path in _EXTENDED_SUITES:
        base_source = _git("show", f"{base}:{path}")
        assert base_source is not None, f"git show failed for {path}"
        current = _REPO_ROOT / path
        current_source = current.read_text(encoding="utf-8") if current.exists() else ""
        gone = sorted(
            set(_TEST_DEF.findall(base_source)) - set(_TEST_DEF.findall(current_source))
        )
        if gone:
            missing[path] = gone

    assert missing == {}


def test_no_theme_token_was_retuned_or_removed():
    """AC 6: PRD-006 could add tokens to the shared theme, never retune one.

    `theme.py` is the one file both surfaces read, so "the chat is untouched"
    depends on it. A line-level diff is the wrong instrument — STORY-009
    extended two CSS selector lists to cover the admin fields, which shows as a
    deletion without changing anything the chat renders. The claim that
    actually matters is value-level, so that is what is asserted.
    """
    base = _base()
    if base is None:
        pytest.skip(f"baseline {_BASE} not resolvable; provenance unverifiable here")

    path = "chat_ui/chat_ui/theme.py"
    base_source = _git("show", f"{base}:{path}")
    assert base_source is not None, "git show failed for theme.py"
    current_source = (_REPO_ROOT / path).read_text(encoding="utf-8")

    def literals(source):
        """Every module-level CONSTANT bound to a literal, parsed not regexed.

        A regex is the obvious tool here and it is wrong: every colour in this
        file is a hex string, so any pattern that also strips trailing `#`
        comments reduces `"#14181C"` to `"` and reports two different palettes
        as identical. This guard was written that way first and passed while a
        retuned INK sat in the tree.
        """
        found = {}
        for node in ast.parse(source).body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    if isinstance(node.value, ast.Constant):
                        found[target.id] = node.value.value
                    elif isinstance(node.value, ast.Name):
                        found[target.id] = f"<alias:{node.value.id}>"
        return found

    before, after = literals(base_source), literals(current_source)

    retuned = {k: (before[k], after[k]) for k in before if k in after and before[k] != after[k]}
    assert retuned == {}, f"existing theme tokens were retuned: {retuned}"
    assert sorted(set(before) - set(after)) == [], "an existing theme token was removed"


def test_the_chat_humanizer_still_renders_what_it_did():
    """AC 6, behavioural half, for the one chat module PRD-006 did edit.

    STORY-002 refactored `formatting._humanize` onto a shared bucket table so
    the register's "2m ago" and the chat's "2 minutes ago" cannot drift apart.
    A refactor of a chat-facing function is exactly where "behaves exactly as
    PRD-004 shipped it" could be lost silently, so the chat's spelling is
    compared against the baseline's implementation span by span, across every
    bucket boundary.
    """
    base = _base()
    if base is None:
        pytest.skip(f"baseline {_BASE} not resolvable; provenance unverifiable here")

    base_source = _git("show", f"{base}:chat_ui/chat_ui/formatting.py")
    assert base_source is not None, "git show failed for formatting.py"

    # The module's relative imports resolve only inside the chat_ui package;
    # strip them, since _humanize depends on none of them.
    stripped = re.sub(r"from \.copy import \([^)]*\)", "", base_source)
    stripped = re.sub(r"from \.[\w.]+ import [^\n]*", "", stripped)
    namespace = {}
    exec(compile(stripped, "<baseline formatting.py>", "exec"), namespace)
    baseline_humanize = namespace["_humanize"]

    from chat_ui.chat_ui.formatting import _humanize as current_humanize

    spans = [0, 1, 2, 59, 60, 61, 119, 120, 3599, 3600, 3601, 7199, 7200]
    spans += [86399, 86400, 86401, 172799, 172800]
    spans += [second * 997 for second in range(200)]

    mismatches = [
        (span, baseline_humanize(span), current_humanize(span))
        for span in spans
        if baseline_humanize(span) != current_humanize(span)
    ]
    assert mismatches == [], f"the chat's relative time changed wording: {mismatches[:5]}"
