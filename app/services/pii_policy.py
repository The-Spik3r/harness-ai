"""The PII policy: which roles, which direction, which entities (PRD-012 Sections 6.2, 6.3, 7/F5).

PII redaction is a policy selected by the same profile name PRD-011 introduced
for patterns. This module holds the policy and nothing else: which roles are
redacted at step 6, whether the response is redacted at step 8, whether fenced
blocks are skipped, which entity types at which threshold, the analyzable
character limit, and whether replacement is structure-safe. It does no
redaction. `pii_redactor.redact_for_policy` (STORY-008) reads a policy, and the
pipeline (STORY-009) resolves one per request.

Three entry points:

- `PiiPolicy`, the frozen description of one policy.
- `get_pii_policy(name)` returns the policy of that name, and `chat` -- the
  strictest -- for any name it does not know (D8). It never raises and never
  logs: it is on the request path. It works before `load()` has run, exactly
  as `pattern_config.get_policy()` does, because the policies are built once at
  import.
- `load()` rebuilds both built-in policies from `settings`, checks them, logs
  one line per pattern profile that falls back to `chat`, and only then
  rebinds. Called once at startup, **after** `pattern_config.load()` -- it
  reads the loaded pattern profiles -- in **both** lifespans (`app/main.py` and
  `chat_ui/chat_ui/chat_ui.py`: the Reflex `api_transformer` mount bypasses the
  former). A test that patches a `PII_*` setting calls `load()` again.

`PII_REDACTION_ENABLED` is not part of a policy. It stays the master switch and
is applied where redaction runs (`redact()`, and `redact_for_policy` in
STORY-008): turning redaction off does not change which policy a profile maps
to.

This module never imports `pii_redactor`. STORY-008's `pii_redactor` imports
`PiiPolicy` from here, and the reverse import would be a cycle. The analyzers
the policies need are prebuilt by `pii_redactor.load()` (STORY-006).
"""

import logging
from dataclasses import dataclass
from typing import Mapping, Optional, get_args

from app.config import settings
from app.models.messages import Role
from app.services import pattern_config

logger = logging.getLogger(__name__)


class PiiConfigError(Exception):
    """Raised by load() for a policy whose fields contradict each other.

    Today there is one check: `skip_fenced_blocks` without `structure_safe`
    (PRD-012 Section 7/F5). Fenced-block skipping is only defined for the
    structure-safe path, where `redact_for_policy` replaces spans itself; the
    `chat` path hands whole texts to `AnonymizerEngine`.

    With only the two built-in policies and validated settings, this is
    essentially unreachable: `code` is always structure-safe and `chat` never
    skips fences. It is reserved for a future policy file (PRD-012 Section 13),
    where an operator could write the combination. Startup fails; there is no
    fallback to another policy.
    """


#: The policy an unknown profile name resolves to (D8). `chat` is the most
#: masking policy, so the fallback moves toward more masking, never less: a
#: custom PRD-011 pattern profile without a PII policy must not inherit the
#: permissive `code` behaviour (PRD-012 Sections 2, 6.2).
FALLBACK_POLICY_NAME = "chat"


@dataclass(frozen=True)
class PiiPolicy:
    """One profile's PII behaviour (PRD-012 Section 6.2).

    | Field                | `chat` (= today)                 | `code`                                    |
    |----------------------|----------------------------------|-------------------------------------------|
    | `input_roles`        | every role                       | user, assistant, tool (+ system, setting) |
    | `output`             | True                             | PII_CODE_REDACT_OUTPUT (False)            |
    | `skip_fenced_blocks` | False                            | PII_CODE_SKIP_CODE_BLOCKS (True)          |
    | `entities`           | PII_ENTITIES                     | PII_ENTITIES_CODE                         |
    | `threshold`          | PII_SCORE_THRESHOLD              | PII_SCORE_THRESHOLD_CODE                  |
    | `max_characters`     | None                             | PII_MAX_CHARACTERS_CODE                   |
    | `structure_safe`     | False                            | True                                      |

    `chat` lists `tool` for completeness only: step 0 refuses `tool` turns, so
    no `chat` request carries one. It lists `system` because today every
    message is redacted, whatever its role, and `chat` must stay today's
    behaviour.
    """

    #: "chat" | "code"
    name: str
    #: Roles whose content is redacted at step 6. PRD-010's `Role`, no second vocabulary.
    input_roles: frozenset[Role]
    #: Redact the response at step 8.
    output: bool
    #: Analyze prose only; fenced blocks pass untouched.
    skip_fenced_blocks: bool
    #: Presidio entity types, in declared order.
    entities: tuple[str, ...]
    threshold: float
    #: Analyzable characters per request; None = no PII-specific limit.
    max_characters: Optional[int]
    #: Quote/backslash/newline-preserving replacement plus JSON-aware mode.
    structure_safe: bool


def _build_chat_policy() -> PiiPolicy:
    """Today's behaviour, byte for byte (PRD-012 Section 2: `chat` does not move)."""
    return PiiPolicy(
        name="chat",
        # Every role in the vocabulary, so a role added to `Role` is redacted
        # under `chat` by default -- the strict direction.
        input_roles=frozenset(get_args(Role)),
        output=True,
        skip_fenced_blocks=False,
        entities=tuple(settings.pii_entities_list),
        threshold=settings.PII_SCORE_THRESHOLD,
        # CONTEXT_MAX_CHARACTERS, checked at step 3, already bounds it.
        max_characters=None,
        # Keeps today's AnonymizerEngine path and so today's exact output.
        structure_safe=False,
    )


def _build_code_policy() -> PiiPolicy:
    """The coding-agent policy (PRD-012 Sections 6.2, 6.3)."""
    # `assistant` is redacted: a /v1 caller writes its own history, so an
    # assistant turn can carry anything (T7). `system` is not, by default: it
    # is the client's own prompt and the largest fixed cost per request (D3).
    roles = {"user", "assistant", "tool"}
    if settings.PII_CODE_REDACT_SYSTEM:
        roles.add("system")
    return PiiPolicy(
        name="code",
        input_roles=frozenset(roles),
        # D1: the reader of a coding agent's output is the file system.
        output=settings.PII_CODE_REDACT_OUTPUT,
        # D2: fenced blocks only; inline backtick spans are still analyzed.
        skip_fenced_blocks=settings.PII_CODE_SKIP_CODE_BLOCKS,
        # D7: pattern recognizers only by default.
        entities=tuple(settings.pii_entities_code_list),
        # D6.
        threshold=settings.PII_SCORE_THRESHOLD_CODE,
        # D4: over it, the request is refused (STORY-010).
        max_characters=settings.PII_MAX_CHARACTERS_CODE,
        structure_safe=True,
    )


def _build_policies() -> dict[str, PiiPolicy]:
    return {policy.name: policy for policy in (_build_chat_policy(), _build_code_policy())}


def _check_consistent(policy: PiiPolicy) -> None:
    """The one combination load() refuses (PRD-012 Section 7/F5); see `PiiConfigError`."""
    if policy.skip_fenced_blocks and not policy.structure_safe:
        raise PiiConfigError(
            f"PII policy {policy.name!r}: skip_fenced_blocks requires structure_safe "
            "(fenced-block skipping is only defined for structure-safe replacement)"
        )


#: The policies in force, by name. Private, and read through `get_pii_policy()`:
#: a public name would be captured by `from app.services.pii_policy import ...`
#: at import time and never see `load()` (the reason `pattern_config._policy`
#: is private). Built at import so the pipeline, and every test that never
#: boots an app, can resolve a policy before `load()` runs.
_policies: Mapping[str, PiiPolicy] = _build_policies()


def get_pii_policy(name: str) -> PiiPolicy:
    """The policy of that name, or `chat` for any name without one (D8).

    Takes a name, never `None`: resolving "no profile passed" to
    `PATTERN_PROFILE_DEFAULT` is `run_conversation`'s job (STORY-009). No I/O
    and no logging -- it runs once per request; the fallback is logged once
    per name, at startup, by `load()`.
    """
    return _policies.get(name, _policies[FALLBACK_POLICY_NAME])


def load() -> None:
    """Rebuild the policies from `settings`, or fail startup with `PiiConfigError`.

    Startup only, after `pattern_config.load()`, in both lifespans. Settings
    are read here, at call time, so a test that patches one and calls load()
    sees it. Every policy is checked before anything is logged or rebound, and
    `_policies` is assigned as the last statement: a failed load leaves the
    previous policies in force (`pattern_config.load()`'s shape).

    Then one INFO line for each profile the loaded pattern policy defines that
    has no PII policy, naming it and the policy it resolves to. It is a
    fallback, not an error, on purpose: requiring every custom pattern profile
    to declare a PII policy would couple two configurations PRD-011 kept apart
    (PRD-012 Section 6.2). Under the built-in pattern policy (`chat`, `code`)
    nothing is logged.
    """
    global _policies

    built = _build_policies()
    for policy in built.values():
        _check_consistent(policy)

    for name in sorted(set(pattern_config.get_policy().profiles) - set(built)):
        logger.info(
            "pii policy: pattern profile %r has no PII policy; it resolves to %r",
            name,
            FALLBACK_POLICY_NAME,
        )

    _policies = built
