"""PRD-006's containment, asserted against git rather than remembered.

STORY-020's job was to prove that the admin console lives entirely inside
`chat_ui/` — no new route, no new query, no schema migration, no new dependency,
and no change to the chat PRD-004 shipped. That proof was a document, and a
document does not fail when someone adds a database function next month. This
file is the same proof, re-run on every suite.

**Why the baseline is a pinned SHA and not `merge-base main HEAD`.**
`tests/test_pii_redaction_integration.py` wrote this guard first, for PRD-003,
and derived its base with `git merge-base main HEAD`. That answers the right
question only while the branch carries one PRD's work. It no longer does:
`epic/PRD-006-admin-console` carries **both** PRD-004 and PRD-006, because
`main` is still at the PRD-003 merge (`56a3781`) and PRD-004 was never merged
into it. Deriving the base here would therefore measure two PRDs at once and
report PRD-004's work as PRD-006's.

That distinction is not academic. Commit `3f553f2` ("feat(chat-ui): implement
PII column migration…", a different author, 2026-08-28) changed
`app/db/database.py` and `app/db/models.py`. It landed **after** PRD-004's own
STORY-019 regression pass certified `app/` clean and **before** PRD-006's first
commit, so `git diff main -- app/` is not empty on this branch and never will
be — through no act of PRD-006's. PRD-006 Section 4 puts every change under
`app/` out of scope, which also forbids *reverting* one; STORY-020 recorded the
attribution and left the code alone. The assertions below are therefore scoped
to what PRD-006 itself did, which is the only claim the evidence supports and
the only one this PRD is accountable for.

The guards skip rather than fail when git or the history is unavailable — a
shallow clone or an exported tree should not turn a provenance check into a red
suite. That concession is inherited from the PRD-003 guard deliberately.
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

# PRD-006 Section 4, out of scope: "Any change under `app/` — no new database
# functions, no query parameters on `GET /audit`, no schema migration, no change
# to `AuditQueryEntry` or `StatsResponse`."
_APP_TREE = "app/"

# PRD-006 Section 8: "No new dependencies in either `requirements.txt`."
_REQUIREMENTS = ("requirements.txt", "chat_ui/requirements.txt")

# PRD-006 Section 9: `/admin/*` is not in the Caddyfile's @backend_routes
# matcher and falls through to the static file_server, so no deployment change
# is required and none was made.
_DEPLOYMENT = ("Caddyfile", "chat_ui/rxconfig.py")

# PRD-006 Section 4, out of scope: "Changes to the chat surface — PRD-004 ships
# as-is." `formatting.py` is deliberately absent: STORY-002 extended it with
# `humanize_compact` for the register's fixed-width time column, sharing one
# bucket table with the chat's `_humanize` so the two spellings cannot drift
# into different ideas of when an hour becomes a day. The chat's own rendering
# is unchanged, and `test_the_chat_humanizer_still_renders_what_it_did` below
# is what holds that — a stricter claim than "the file was not touched".
_CHAT_MODULES = (
    "chat_ui/chat_ui/state.py",
    "chat_ui/chat_ui/copy.py",
    "chat_ui/chat_ui/models.py",
    "chat_ui/chat_ui/components/chat.py",
    "chat_ui/chat_ui/components/bubbles.py",
    "chat_ui/chat_ui/components/shell.py",
)

# PRD-006 Section 15, "Tests that must pass unmodified". Six of the eight are
# byte-unmodified; `test_copy.py` and `test_contrast.py` are the two this PRD's
# own stories were allowed to extend, so they are asserted by census instead
# (see below) — byte-equality would be the wrong assertion and would have to be
# deleted the first time it fired, which is how a guard becomes decoration.
_UNMODIFIED_SUITES = (
    "tests/test_admin_auth.py",
    "tests/test_audit_router.py",
    "tests/test_stats_router.py",
    "tests/test_db.py",
    "tests/test_route_reservations.py",
    "tests/test_chat_state.py",
)

_EXTENDED_SUITES = ("tests/test_copy.py", "tests/test_contrast.py")

_TEST_DEF = re.compile(r"^def (test_\w+)", re.MULTILINE)


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


def _changed_since_base(*paths):
    base = _base()
    if base is None:
        pytest.skip(f"baseline {_BASE} not resolvable; provenance unverifiable here")
    out = _git("diff", "--name-only", base, "--", *paths)
    assert out is not None, f"git diff failed for {paths}"
    return [line for line in out.splitlines() if line.strip()]


def test_no_file_under_app_changed_since_prd_006_began():
    """AC 2: the console added no database function, query parameter or migration.

    Scoped to PRD-006's own baseline, not to `main` — see the module docstring
    for the commit that makes those two questions different.
    """
    assert _changed_since_base(_APP_TREE) == []


def test_no_new_dependency_in_either_requirements_file():
    """AC 3: neither requirements file gained a line."""
    assert _changed_since_base(*_REQUIREMENTS) == []


def test_the_caddyfile_and_rxconfig_are_unchanged():
    """AC 4: `/admin/*` needed no deployment or Reflex config change."""
    assert _changed_since_base(*_DEPLOYMENT) == []


def test_the_chat_modules_are_unchanged_since_prd_006_began():
    """AC 6, structural half: no chat module was edited to serve the console."""
    assert _changed_since_base(*_CHAT_MODULES) == []


@pytest.mark.parametrize("path", _UNMODIFIED_SUITES)
def test_the_pinned_suites_are_byte_unmodified(path):
    """AC 1: the six suites PRD-006 promised never to open."""
    assert _changed_since_base(path) == []


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
