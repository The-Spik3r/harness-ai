"""The pattern policy: where it comes from, and what stops the boot (PRD-011 Section 7/F3).

This module owns **all** of the I/O and all of the configuration reading behind
pattern detection. `pattern_detector.py` stays pure -- it compiles one pattern
and strips one message's code spans and reads nothing -- and everything that
needs a setting, a file or a policy lives here (PRD-011 Section 6.9).

Three entry points:

- `load()` reads `PATTERNS_FILE` and **replaces the built-in policy wholesale**.
  No merge, ever. A list in the built-in policy and absent from the file is
  gone. That is `authz.load()`'s rule and it is here for `authz.load()`'s
  reason (PRD-011 Section 6.3): a merge means an operator who deletes a pattern
  from their file still has it in force, and cannot tell what is in force by
  reading the file. An empty setting reads no file at all and the built-in
  policy stands.
- `get_policy()` returns whatever is in force, and returns the built-in policy
  when `load()` has never run -- `ROLE_PERMISSIONS` before `authz.load()`,
  exactly.
- `get_profile(name)` returns one profile from whatever is in force, and
  raises `PatternConfigError` for a name the policy does not define.

Called once at startup, by STORY-007, in **both** lifespans (`app/main.py` and
`chat_ui/chat_ui/chat_ui.py`: the Reflex `api_transformer` mount bypasses the
former entirely, which is why `init_db()` and `authz.load()` are already
registered twice). Never per request. The first reader of a compiled pattern is
`inspect()` in STORY-008.

Profiles and the role inspection matrix (PRD-011 Section 6.4), the `roles:`
vocabulary, `PATTERN_PROFILE_DEFAULT`'s cross-check and `get_profile()` are
STORY-006's, built on STORY-005's lists. What is deliberately **not** here: the
message walk and what a hit does -- `inspect()` in STORY-008.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, get_args

import yaml

from app.config import settings
from app.models.messages import Role
from app.services.pattern_detector import (
    PatternCompileError,
    compile_pattern,
    has_nested_quantifier,
)


class PatternConfigError(Exception):
    """Raised by load() for every way PATTERNS_FILE can be wrong: unreadable,
    unparseable, an unknown key, an unknown `match` or `scope`, an empty list,
    a profile naming a list nobody defined, a `roles:` map that is empty or
    names an unknown role or action, a regex that is forbidden, uncompilable or
    catastrophic, or a `PATTERN_PROFILE_DEFAULT` the policy does not define.
    Also raised by `get_profile()` for an unknown name.

    Startup fails. There is no silent fallback to the built-in policy -- a
    deployment that thinks it is running its own list and is not is the failure
    this exception exists to prevent (PRD-011 Sections 6.3, 6.9).

    It is also the outer half of a two-exception seam. `compile_pattern` raises
    `PatternCompileError`, which cannot name a list because `pattern_detector`
    is pure and does not know where a pattern came from; load() catches it and
    re-raises this with the list name attached, which is the error an operator
    actually reads at startup (`pattern_detector.PatternCompileError`).
    """


# The closed vocabularies. Every one of these is validated against explicitly
# rather than by trying and seeing what happens, because the error an operator
# needs names the allowed values -- `compile_pattern` would reject `match:
# words` on its own, but its message cannot say which list it came from.
_MATCH_MODES = ("word", "regex")
_SCOPES = ("everywhere", "outside_code")

_TOP_LEVEL_KEYS = frozenset({"lists", "profiles"})
_LIST_KEYS = frozenset({"match", "scope", "patterns"})
_PROFILE_KEYS = frozenset({"lists", "roles"})

#: The role vocabulary is `app.models.messages.Role` and nothing else -- this
#: module introduces no second role literal (PRD-011 Section 6.2). A role added
#: there is accepted in a `roles:` map here with no edit to this file.
_ROLES = get_args(Role)
_ACTIONS = ("block", "flag")

#: What a profile does with a hit in a role it inspects: `block` refuses the
#: request, `flag` audits it and lets it continue (PRD-011 Section 4). STORY-008's
#: `PatternHit.action` carries the same two values -- note that
#: `pattern_detector` cannot import this alias, because this module imports it.
Action = Literal["block", "flag"]


@dataclass(frozen=True)
class PatternList:
    """One named list of patterns sharing a match mode and a scope (PRD-011 Section 6.2).

    `patterns` and `compiled` are positional parallels: `compiled[i]` is
    `patterns[i]`. Both are tuples because declared order is load-bearing --
    `inspect()` reports lists in declared order and patterns in declared order
    (PRD-011 Section 7/F5), and the built-in `keywords` list depends on it:
    `admin mode` precedes `override`, so "please override and enable admin
    mode" reports `admin mode`.
    """

    name: str
    match: Literal["word", "regex"]
    scope: Literal["everywhere", "outside_code"]
    patterns: tuple[str, ...]
    #: Built at load, never at request time (PRD-011 Section 6.2).
    compiled: tuple[re.Pattern, ...]


@dataclass(frozen=True)
class Profile:
    """A named set of lists plus the roles it inspects (PRD-011 Sections 6.2, 6.4).

    **A role absent from `roles` is not inspected.** This is the opposite
    default from `authz.py`, where an absent permission denies: RBAC decides
    permission and this decides inspection, and inspecting nothing by default
    is the safe direction for a false-positive-prone check (PRD-011 Section
    7/F4). A reader who knows `authz.py` will assume deny-by-default here and
    be wrong.

    `lists` holds resolved `PatternList` objects, not names, so an undefined
    list name is a startup error and can never surface as a request-time
    `KeyError`.

    `roles` is validated at load: every key must be a member of
    `app.models.messages.Role` -- this module introduces no second role
    vocabulary -- and every value `block` or `flag`. An empty map is a startup
    error, not a profile that inspects nothing (PRD-011 Section 9.2, T5). It is
    held as a plain `dict` in declared order; `frozen=True` stops it being
    reassigned, not mutated, which is all PRD-011 Section 6.2 asks.

    Under the built-in `code` profile, `system` is not inspected on purpose: it
    is the client's own prompt, and the richest source of false positives
    (STORY-011 demonstrates it). PRD-014 is where that cell may change -- see
    the comment on the `code` profile in `_build_built_in()`.
    """

    name: str
    lists: tuple[PatternList, ...]
    roles: Mapping[Role, Action]


@dataclass(frozen=True)
class PatternPolicy:
    """Everything in force at once: the lists by name, and the profiles by name.

    `frozen=True` stops the policy being edited in place; it does not deep-freeze
    the mappings, and is not meant to. What must be immutable is declared order,
    and that lives in the tuples inside `PatternList` and `Profile`.
    """

    lists: Mapping[str, PatternList]
    profiles: Mapping[str, Profile]


def _built_in_list(
    name: str,
    match: str,
    scope: str,
    patterns: tuple[str, ...],
) -> PatternList:
    return PatternList(
        name=name,
        match=match,
        scope=scope,
        patterns=patterns,
        compiled=tuple(compile_pattern(pattern, match) for pattern in patterns),
    )


def _build_built_in() -> PatternPolicy:
    """The policy a deployment gets when it configures nothing (PRD-011 Sections 6.3, 6.4).

    The seven patterns are pre-PRD-011's `SUSPICIOUS_PATTERNS`, split into two
    lists because the split is the whole point of decision D3: the four
    injection phrases are things nobody writes by accident, in code or out of
    it, so they carry `scope: everywhere`; the three keywords are ordinary
    source vocabulary, so they carry `scope: outside_code` and the `code`
    profile does not load them at all.

    They are **copied** from `pattern_detector.SUSPICIOUS_PATTERNS` rather than
    imported from it, deliberately: STORY-008 deletes that constant, and an
    import here would make this policy depend on something scheduled for
    removal. `tests/test_pattern_config.py` asserts the two agree for as long
    as both exist.

    Order within each list is load-bearing, not cosmetic -- see `PatternList`.
    """
    injection = _built_in_list(
        "injection",
        "word",
        "everywhere",
        (
            "ignore previous instructions",
            "forget everything",
            "show system prompt",
            "reveal password",
        ),
    )
    keywords = _built_in_list(
        "keywords",
        "word",
        "outside_code",
        (
            "execute code",
            "admin mode",
            "override",
        ),
    )

    return PatternPolicy(
        lists={"injection": injection, "keywords": keywords},
        profiles={
            "chat": Profile(
                name="chat",
                lists=(injection, keywords),
                roles={"user": "block"},
            ),
            # `system` is not inspected here on purpose: under `code` the system
            # turn is the client's own prompt, authored by OpenCode or Cline
            # rather than by an attacker upstream of them, and it is the single
            # richest source of false positives -- all three keywords appear in
            # real agent system prompts. A deployment that distrusts its clients
            # adds `system: block` to its own profile. This is the default, not
            # a ceiling (PRD-011 Section 6.4).
            #
            # `tool` flags rather than blocks because nobody has run the flag in
            # production yet; promoting it is a default change, not a code
            # change (PRD-011 Section 6.4, D4).
            "code": Profile(
                name="code",
                lists=(injection,),
                roles={"user": "block", "tool": "flag"},
            ),
        },
    )


#: The policy in force when nothing is configured. Public and never rebound --
#: `load()` rebinds `_policy`, not this -- so a test, and STORY-007's assertion
#: that `examples/patterns.yaml` parses to the same thing, can name it.
BUILT_IN_POLICY = _build_built_in()

#: The policy in force. Private, and read through `get_policy()`: a public name
#: would be captured by `from app.services.pattern_config import POLICY` at
#: import time and never see the loaded file (PRD-011 Section 7/F3).
_policy = BUILT_IN_POLICY


def get_policy() -> PatternPolicy:
    """The policy in force -- the built-in one until `load()` replaces it.

    Returns rather than raises when `load()` has never run. The pipeline
    (STORY-008) and every test that never boots an app depend on that, exactly
    as `authz.ROLE_PERMISSIONS` stands on its own before `authz.load()` runs.
    """
    return _policy


def get_profile(name: str) -> Profile:
    """The named profile from the policy in force, or `PatternConfigError`.

    Reads the loaded policy, not `BUILT_IN_POLICY`, and does no I/O -- it is on
    STORY-008's request path, under the rule `get_policy()` follows. Raises the
    same error type `load()` does (PRD-011 Section 10). In practice that only
    happens for a call-site bug: `load()` has already proven
    `PATTERN_PROFILE_DEFAULT` exists, and PRD-014's `"code"` is a literal.

    Takes a name, never `None`: resolving "no profile passed" to the default is
    `run_conversation`'s job (PRD-011 Section 6.6).
    """
    profiles = _policy.profiles
    if name not in profiles:
        raise PatternConfigError(
            f"unknown pattern profile {name!r} (defined profiles: {_allowed(profiles)})"
        )
    return profiles[name]


# --- Validation ------------------------------------------------------------
#
# Every message below names the file, the offending node and the rule that
# failed, and enumerates the allowed values where there is a closed set -- the
# shape `authz.py` uses for an unrecognized permission. The path is in every
# message because an operator debugging a failed startup has a path in an
# environment variable and a traceback in a log, and joining the two by hand is
# work the message can do for them.
#
# Pattern *text* may appear in these messages, unlike
# `MessageNormalizationError`, which withholds the content it rejects. The
# difference is real: a configured pattern is operator-authored configuration,
# not untrusted request content, and a startup error that will not say which
# pattern failed is useless.


def _fail(path: str, *parts: str) -> PatternConfigError:
    return PatternConfigError(f"PATTERNS_FILE '{path}': " + ": ".join(parts))


def _allowed(values) -> str:
    return ", ".join(sorted(values))


def _check_keys(path: str, where: str, body: Mapping, allowed, required) -> None:
    """Unknown keys and missing keys, reported separately.

    Unknown-key rejection is what turns `mach: word` into a named error instead
    of a list that silently loses its match mode. Requiring every key is the
    same instinct one step further: a `scope` that defaults rather than being
    written is a policy an operator cannot read off the file, which is the
    failure wholesale replacement exists to avoid (PRD-011 Section 6.3).
    """
    unknown = sorted(set(body) - set(allowed))
    if unknown:
        raise _fail(
            path,
            where,
            f"unknown key {unknown[0]!r} (expected one of: {_allowed(allowed)})",
        )

    missing = sorted(set(required) - set(body))
    if missing:
        raise _fail(
            path,
            where,
            f"missing key {missing[0]!r} (required: {_allowed(required)})",
        )


def _parse_patterns(path: str, where: str, raw) -> tuple[str, ...]:
    # A bare string is the easy YAML slip -- `patterns: override` reads as one
    # string, and iterating it would silently configure seven single-character
    # patterns. Refused by name rather than by accident.
    if isinstance(raw, str) or not isinstance(raw, (list, tuple)):
        raise _fail(path, where, "patterns must be a list of strings")

    if not raw:
        # PRD-011 Section 9.2, T5: nothing loads and inspects nothing by
        # accident -- only by writing it out.
        raise _fail(path, where, "patterns is empty")

    for pattern in raw:
        if not isinstance(pattern, str) or not pattern.strip():
            raise _fail(path, where, f"pattern {pattern!r} is not a non-empty string")

    return tuple(raw)


def _compile_all(path: str, where: str, match: str, patterns: tuple[str, ...]):
    compiled = []
    for pattern in patterns:
        try:
            compiled.append(compile_pattern(pattern, match))
        except PatternCompileError as exc:
            # The seam: `pattern_detector` names the pattern and the engine's
            # complaint, and this adds the list the pattern came from.
            raise _fail(path, where, str(exc)) from exc

        # After compiling, not before: a pattern that is both uncompilable and
        # textually nested is better reported as a syntax error, which is what
        # the operator has. Compiling a catastrophic pattern does not run it.
        if match == "regex" and has_nested_quantifier(pattern):
            raise _fail(
                path,
                where,
                f"regex pattern {pattern!r} has a nested quantifier and is refused at "
                "startup (PATTERNS_ALLOW_REGEX does not override this; rewrite the "
                "pattern without a quantified group whose body is itself quantified)",
            )

    return tuple(compiled)


def _parse_lists(path: str, raw) -> dict[str, PatternList]:
    if not isinstance(raw, Mapping):
        raise _fail(path, "lists", "must be a mapping of list name to list body")
    if not raw:
        raise _fail(path, "lists", "is empty")

    lists: dict[str, PatternList] = {}
    for name, body in raw.items():
        where = f"list {name!r}"
        if not isinstance(body, Mapping):
            raise _fail(path, where, "must be a mapping")

        _check_keys(path, where, body, _LIST_KEYS, _LIST_KEYS)

        match = body["match"]
        if match not in _MATCH_MODES:
            raise _fail(
                path, where, f"unknown match {match!r} (expected one of: {_allowed(_MATCH_MODES)})"
            )

        scope = body["scope"]
        if scope not in _SCOPES:
            raise _fail(
                path, where, f"unknown scope {scope!r} (expected one of: {_allowed(_SCOPES)})"
            )

        # Per list, before a single pattern is compiled: a forbidden list
        # reports once and names the setting to change. Off by default is the
        # first of PRD-011 Section 9.2 T4's four ReDoS layers, and enabling it
        # is meant to be a deliberate act.
        if match == "regex" and not settings.PATTERNS_ALLOW_REGEX:
            raise _fail(
                path, where, "match: regex requires PATTERNS_ALLOW_REGEX=true"
            )

        patterns = _parse_patterns(path, where, body["patterns"])
        lists[name] = PatternList(
            name=name,
            match=match,
            scope=scope,
            patterns=patterns,
            compiled=_compile_all(path, where, match, patterns),
        )

    return lists


def _parse_roles(path: str, where: str, raw) -> dict[Role, Action]:
    # A bare `roles:` line with its entries forgotten parses to None. "Empty" is
    # the true diagnosis of that slip, so it is reported as one rather than as
    # a type error.
    if raw is None or (isinstance(raw, Mapping) and not raw):
        # PRD-011 Section 9.2, T5: a profile that inspects nothing must be
        # written out, not arrived at -- and there is no way to write it out
        # short of deleting the profile.
        raise _fail(
            path,
            where,
            "roles is empty (a profile must inspect at least one role; "
            "a role absent from roles is not inspected)",
        )
    if not isinstance(raw, Mapping):
        raise _fail(path, where, "roles must be a mapping of role to action")

    # Declared order, first offender reported -- `_check_keys`'s `unknown[0]`.
    # Exact match, no case folding: the vocabulary is exact, as `match` and
    # `scope` are. A YAML key such as `yes:` arrives as a bool and is refused
    # here like any other stranger, with its parsed value in the message.
    for role, action in raw.items():
        if role not in _ROLES:
            raise _fail(
                path,
                where,
                f"roles: unknown role {role!r} (expected one of: {_allowed(_ROLES)})",
            )
        if action not in _ACTIONS:
            raise _fail(
                path,
                where,
                f"roles: role {role!r} has unknown action {action!r} "
                f"(expected one of: {_allowed(_ACTIONS)})",
            )

    return dict(raw)


def _parse_profiles(path: str, raw, lists: Mapping[str, PatternList]) -> dict[str, Profile]:
    """Profiles, each checked in this order (PRD-011 Sections 6.2, 7/F4, 9.2 T5).

    1. The section exists and is a non-empty mapping; each profile is a mapping.
    2. Its keys are known, and both `lists` and `roles` are present.
    3. `lists:` is a non-empty list, and every name in it resolves to a defined
       list -- resolved to objects at load, so an undefined name is a startup
       error and never a request-time `KeyError`.
    4. `roles:` is a non-empty mapping, every key a member of
       `app.models.messages.Role` and every value `block` or `flag`.

    `PATTERN_PROFILE_DEFAULT`'s cross-check is not here: it is a rule about the
    whole policy, not one profile, and it must also run when no file is read at
    all. `load()` owns it.
    """
    if not isinstance(raw, Mapping):
        raise _fail(path, "profiles", "must be a mapping of profile name to profile body")
    if not raw:
        # PRD-011 Section 9.2, T5, again: a file with no profiles inspects
        # nothing, and that must be written out rather than arrived at.
        raise _fail(path, "profiles", "is empty")

    profiles: dict[str, Profile] = {}
    for name, body in raw.items():
        where = f"profile {name!r}"
        if not isinstance(body, Mapping):
            raise _fail(path, where, "must be a mapping")

        # Both keys required: an absent `roles:` would otherwise be an empty
        # map by another name, and T5 refuses that.
        _check_keys(path, where, body, _PROFILE_KEYS, _PROFILE_KEYS)

        names = body["lists"]
        if isinstance(names, str) or not isinstance(names, (list, tuple)):
            raise _fail(path, where, "lists must be a list of list names")
        if not names:
            raise _fail(path, where, "lists is empty")

        resolved = []
        for list_name in names:
            if list_name not in lists:
                raise _fail(
                    path,
                    where,
                    f"names undefined list {list_name!r} (defined lists: {_allowed(lists)})",
                )
            resolved.append(lists[list_name])

        profiles[name] = Profile(
            name=name,
            lists=tuple(resolved),
            roles=_parse_roles(path, where, body["roles"]),
        )

    return profiles


def _check_default_profile(profiles: Mapping[str, Profile], source: str, note: str = "") -> None:
    """`PATTERN_PROFILE_DEFAULT` must name a profile the policy defines (PRD-011 Section 9.3).

    A cross-check between a setting and a file, which is why it lives here and
    not in a pydantic validator: the file is not read when `Settings` is
    constructed (`app/config.py`, at the field). Read at call time, never at
    import, so a test's `monkeypatch.setattr(settings, ...)` is seen.
    """
    default = settings.PATTERN_PROFILE_DEFAULT
    if default not in profiles:
        raise PatternConfigError(
            f"PATTERN_PROFILE_DEFAULT {default!r} names a profile {source} does not "
            f"define (defined profiles: {_allowed(profiles)}){note}"
        )


def load() -> None:
    """Read PATTERNS_FILE and replace the policy wholesale, or fail startup.

    An empty `PATTERNS_FILE` is a no-op: the built-in policy stands and **no
    file is read**. Otherwise every rule below must pass before anything is
    rebound -- `_policy` is assigned as the last statement, so a file that
    fails rule nine leaves the previous policy intact rather than a half-built
    one (`authz.load()`'s shape, PRD-011 Section 6.9).

    Called once at startup by STORY-007, in both lifespans. Never per request:
    every pattern is compiled here, so that a request-time match is a
    `re.Pattern.search` and nothing more.

    `yaml.safe_load` only, which also refuses the `!!python/...` tags that make
    YAML loading dangerous; a writable `PATTERNS_FILE` is the trust boundary
    `RBAC_ROLES_FILE` already sits on and claims no new mitigation (PRD-011
    Section 9.2, T7).

    One documented limit: PyYAML resolves duplicate mapping keys silently,
    last one winning, so a file with `lists:` written twice loses one of them
    with no error. Detecting it needs a custom loader; if a second YAML config
    arrives (PRD-015), a shared strict loader is the place to fix it once.

    `PATTERN_PROFILE_DEFAULT` is cross-checked against the profiles about to be
    in force on **both** paths. With a file, after the profiles parse and
    before `_policy` is rebound, so a bad default leaves the previous policy
    intact like any other rule. With no file, against the built-in policy --
    still reading no file -- because a boot that succeeds and then fails on the
    first request that needs the default is exactly the request-time failure
    PRD-011 Section 2 forbids.
    """
    global _policy

    path = settings.PATTERNS_FILE
    if not path:
        _check_default_profile(
            BUILT_IN_POLICY.profiles, "the built-in policy", "; PATTERNS_FILE is unset"
        )
        return

    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise PatternConfigError(f"Failed to read PATTERNS_FILE '{path}': {exc}") from exc

    try:
        document = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise PatternConfigError(f"Failed to parse PATTERNS_FILE '{path}': {exc}") from exc

    # An empty file parses to None and a bare scalar to a str; neither may
    # reach `.items()` and die as an AttributeError three frames down.
    if not isinstance(document, Mapping):
        raise _fail(path, "document", "must be a mapping with 'lists' and 'profiles' sections")

    _check_keys(path, "document", document, _TOP_LEVEL_KEYS, _TOP_LEVEL_KEYS)

    lists = _parse_lists(path, document["lists"])
    profiles = _parse_profiles(path, document["profiles"], lists)
    _check_default_profile(profiles, f"PATTERNS_FILE '{path}'")

    _policy = PatternPolicy(lists=lists, profiles=profiles)
