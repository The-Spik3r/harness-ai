"""Release the calls the policy allowed, drop the ones it denied with a note (PRD-017 Section 6.6; D1, D2, D9, D14).

`apply_decisions(calls, decisions)` takes one response's tool calls and their
`ActionDecision`s (from `action_policy.evaluate_all`, same order) and returns a
frozen `Release`: the `allow` and `flag` calls (a `flag` is released and logged,
PRD-016 D10 / PRD-017 D9; the very same `ToolCallSpec` objects, in model
order, `arguments` untouched, D13), one note per `deny`, and the response's
`finish_reason`.

Decisions are matched to calls by position and then by `tool_call_id ==
call.id` at that position. Upstream ids can repeat across rounds, but STORY-004
refuses a duplicate id within one response, so position plus id equality is
enough. A length mismatch, a reordered or foreign decision list, or a decision
outside `allow`/`flag`/`deny` is a programming error and raises `ValueError`
(T1: no call is ever released undecided). Messages name the position and the
rule, never an id, a name or a decided value (PRD-015 T6, T9).

The note is `DENIAL_NOTE_TEMPLATE` with the model-chosen `name` and `id` cut to
`NOTE_FIELD_CAP` and PRD-016's `reason` inserted unchanged (it is already safe
for the agent, PRD-016 T11). `content_with_notes` is the one Section 6.6
joining helper; STORY-010 calls it after step 8 redaction so a note is never
masked, and the response shapes (STORY-011/012) do not re-join. Mapping `""` to
`null` is the result translator's (STORY-011). `ToolOutcome` is what step 7c
hands the router on the success result (STORY-010).

Purity (Section 6.12): this module names no `settings`, does no I/O, logs
nothing and reads no clock. `ActionDecision` is imported for typing only, so
importing this module loads nothing but `app.models.messages`.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Sequence

from app.models.messages import ToolCallSpec

if TYPE_CHECKING:
    from app.services.action_policy import ActionDecision

#: One sentence per denied call (PRD-017 Section 6.6); the single source the
#: docs and the E2E assertions cite.
DENIAL_NOTE_TEMPLATE = "[harness] tool call {name} ({id}) was denied: {reason}"

#: `name` and `id` are model-chosen; in a note each is cut to this length
#: (the same cut as `action_policy._NAME_DETAIL_CAP`).
NOTE_FIELD_CAP = 64

#: Written out, not imported from `action_classifiers`, to keep this module's
#: only runtime `app` import `app.models.messages`; a test pins it to `DECISIONS`.
_DECISIONS = frozenset({"allow", "flag", "deny"})
_RELEASED = frozenset({"allow", "flag"})


@dataclass(frozen=True)
class Release:
    """What leaves the harness for one response (PRD-017 Section 6.6)."""

    #: The `allow` and `flag` calls, in model order, unmodified.
    tool_calls: tuple[ToolCallSpec, ...]
    #: One denial note per `deny`, in model order.
    notes: tuple[str, ...]
    #: `"tool_calls"` if any call is released, `"stop"` if every call was
    #: denied, `None` when there were no calls (the upstream's stands).
    finish_reason: Optional[str]


@dataclass(frozen=True)
class ToolOutcome:
    """Step 7c's result for one response: what the router may release (PRD-017 Section 6.1)."""

    release: Release
    #: `evaluate_all`'s decisions, in call order, one per upstream call.
    decisions: tuple["ActionDecision", ...]


def apply_decisions(
    calls: Sequence[ToolCallSpec], decisions: Sequence["ActionDecision"]
) -> Release:
    """Split `calls` into released calls and denial notes (PRD-017 Section 6.6).

    Raises `ValueError` when the lists differ in length, a decision's
    `tool_call_id` is not its call's `id`, or a decision is not
    allow/flag/deny. Every pair is checked before anything is built, so a bad
    list never yields a partial release.
    """
    if len(calls) != len(decisions):
        raise ValueError(
            f"apply_decisions: {len(calls)} calls but {len(decisions)} decisions; "
            "one decision per call, in order"
        )
    for index, (call, decision) in enumerate(zip(calls, decisions)):
        if decision.tool_call_id != call.id:
            raise ValueError(
                f"apply_decisions: decisions[{index}].tool_call_id does not match "
                f"calls[{index}].id; decisions must be in call order"
            )
        if decision.decision not in _DECISIONS:
            raise ValueError(
                f"apply_decisions: decisions[{index}].decision is not allow, flag or deny"
            )

    released = []
    notes = []
    for call, decision in zip(calls, decisions):
        if decision.decision in _RELEASED:
            released.append(call)
        else:
            notes.append(
                DENIAL_NOTE_TEMPLATE.format(
                    name=call.name[:NOTE_FIELD_CAP],
                    id=call.id[:NOTE_FIELD_CAP],
                    reason=decision.reason,
                )
            )
    if not calls:
        finish_reason = None
    else:
        finish_reason = "tool_calls" if released else "stop"
    return Release(tuple(released), tuple(notes), finish_reason)


def content_with_notes(content: str, notes: Sequence[str]) -> str:
    """Join the (redacted) content and the denial notes (PRD-017 Section 6.6).

    `""` with no notes stays `""`; the result translator maps it to `null` (STORY-011).
    """
    return "\n\n".join(filter(None, [content, *notes]))
