"""What the model is doing, read off the stream (PRD-021 Sections 6.1, 6.2; D6, T1, T4).

`phase_of` maps one upstream event to the phase a reader is told about, and
nothing else: it never sees, returns or stores text. A phase carries a kind
(`shell`, `sql`, ...), never a command or an argument (T4), so a tool call
shows up to a reader only as "preparing an action of this kind".

Pure: this module reads no settings and does no I/O. It imports the event
types, the phase vocabulary and `OperationKind` only. The pipeline builds the
`tool_kinds` mapping per request from the action policy and passes it in.
"""

from typing import Mapping, Optional

from app.services.action_classifiers import OperationKind
from app.services.delivery import PhaseName
from app.services.upstream.types import ReasoningDelta, TextDelta, ToolCallDelta, UpstreamEvent


def phase_of(
    event: UpstreamEvent,
    previous: Optional[PhaseName],
    tool_kinds: Optional[Mapping[str, OperationKind]] = None,
) -> Optional[tuple[PhaseName, Optional[OperationKind]]]:
    """The `(phase, action_kind)` this event moves the reader to, or None for no change.

    `previous` is the last phase emitted (None before any). Empty text and
    empty reasoning, a tool-call fragment without a name, usage and finish
    events yield None; so does an event that leaves the phase unchanged, so a
    second named call does not emit `preparing_action` again. `action_kind` is
    set only for `preparing_action`, from `tool_kinds` (None for an unmapped tool).
    """
    phase: Optional[PhaseName] = None
    kind: Optional[OperationKind] = None
    if isinstance(event, ReasoningDelta):
        if event.text != "":
            phase = "thinking"
    elif isinstance(event, TextDelta):
        if event.text != "":
            phase = "writing"
    elif isinstance(event, ToolCallDelta):
        if event.name:
            phase = "preparing_action"
            kind = (tool_kinds or {}).get(event.name)
    if phase is None or phase == previous:
        return None
    return phase, kind
