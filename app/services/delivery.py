"""The delivery seam between the pipeline and a reader of its progress (PRD-021 Sections 6.1, 6.3, 6.4; D18, T10).

`run_conversation` takes an optional `DeliverySink` and tells it what is
happening: which stage of the pipeline is running, which phase the model is in,
and -- in STORY-006 and later -- the content and reasoning as they are produced.
This module is the vocabulary of that conversation and nothing else:

- `StageName` and `PhaseName`, closed vocabularies (PRD 7.1).
- One frozen event dataclass per sink method, for consumers that read a queue.
- `DeliverySink`, the protocol the pipeline writes to.
- `Visibility`, the step 2d verdict: what this request may show its reader.
- `QueueSink`, the implementation the router and the chat UI use: it hands each
  event to the event loop with `call_soon_threadsafe` and never blocks.

**The pipeline decides, the sink obeys.** Filtering by permission happens at
step 2d (`Visibility.compute`), not in a sink: a sink that never receives a
content call cannot leak one. Stage events depend on configuration only (T10):
never on a finding, an entity count or a verdict, so a reader cannot learn from
the event list what the checks concluded.

Pure: this module reads no settings and does no I/O. The pipeline reads the
settings and the grants per request and passes the values in, as
`v1_sse.py` does. It imports `OperationKind` from `action_classifiers`, whose
package imports only dataclasses and typing.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Literal, Optional, Protocol, Union, get_args

from app.services.action_classifiers import OperationKind

# The seven stages a reader may be told about (PRD 7.1). Steps 2b, 3 and 7 are
# not named: 2b emits nothing and 3/7 are not progress a reader acts on.
StageName = Literal[
    "checking_permissions",
    "checking_usage",
    "checking_duplicates",
    "inspecting_prompt",
    "masking_input",
    "evaluating_actions",
    "masking_output",
]
STAGE_NAMES = get_args(StageName)

# What the model is doing, as a reader sees it (PRD 7.1). `phase_of` is STORY-006's.
PhaseName = Literal["waiting", "thinking", "writing", "preparing_action"]
PHASE_NAMES = get_args(PhaseName)

# The doors a Visibility may be computed for. Mirrors `query_pipeline.Ingress`,
# restated as a plain string compare so this module imports nothing from it.
_CHAT_INGRESS = "chat"


class DeliverySink(Protocol):
    """What the pipeline writes to (PRD 6.3). Every method must return quickly
    and may be called from a worker thread; the pipeline swallows a fault."""

    def stage(self, name: StageName) -> None: ...

    def phase(self, name: PhaseName, action_kind: Optional[OperationKind] = None) -> None: ...

    # Only ever called when `Visibility.realtime`.
    def content(self, text: str) -> None: ...

    # Only when `Visibility.reasoning` and `Visibility.realtime`.
    def reasoning(self, text: str) -> None: ...

    # The upstream stream opened: the commit signal (PRD 6.3, last bullet).
    def committed(self, completion_id: str) -> None: ...


@dataclass(frozen=True)
class StageEvent:
    name: StageName


@dataclass(frozen=True)
class PhaseEvent:
    name: PhaseName
    action_kind: Optional[OperationKind] = None


@dataclass(frozen=True)
class ContentEvent:
    text: str


@dataclass(frozen=True)
class ReasoningEvent:
    text: str


@dataclass(frozen=True)
class CommittedEvent:
    completion_id: str


DeliveryEvent = Union[StageEvent, PhaseEvent, ContentEvent, ReasoningEvent, CommittedEvent]


@dataclass(frozen=True)
class Visibility:
    """Step 2d (PRD 6.1, F3): what this request may show its reader.

    - `realtime`: content may be forwarded as it is produced.
    - `reasoning`: reasoning may be forwarded. Independent of `realtime`
      (PRD 6.4): buffered SSE can still carry reasoning.
    - `upstream_streamed`: the call upstream is made as a stream, whether or
      not anything is forwarded live (the chat door streams for its progress
      words even without a grant).
    """

    realtime: bool
    reasoning: bool
    upstream_streamed: bool

    @classmethod
    def compute(
        cls,
        *,
        streaming_enabled: bool,
        holds_realtime: bool,
        holds_reasoning: bool,
        caps: Any,
        ingress: Optional[str],
        streamed: bool = True,
    ) -> "Visibility":
        """Pure. `caps` is a `provider_registry.Capabilities` (only `.streaming`
        and `.reasoning` are read). The grants come from `authz.holds()`, never
        `authorize()` (T8). `ingress` may be None (a direct caller): then
        `upstream_streamed` depends only on the grants.

        PRD-021 6.4 (STORY-010): `/v1` with `stream: false` is never real time,
        whatever the grants say, so `streamed=False` on that ingress clears
        `realtime` (and `upstream_streamed` follows). Every other caller keeps
        the default and the rule above."""
        realtime = streaming_enabled and holds_realtime and caps.streaming
        if ingress == "v1" and not streamed:
            realtime = False
        reasoning = streaming_enabled and holds_reasoning and caps.reasoning
        upstream_streamed = (
            streaming_enabled
            and caps.streaming
            and (realtime or reasoning or ingress == _CHAT_INGRESS)
        )
        return cls(realtime=realtime, reasoning=reasoning, upstream_streamed=upstream_streamed)


class QueueSink:
    """A `DeliverySink` that puts events on an unbounded `asyncio.Queue` (PRD 6.3).

    The pipeline runs in an executor thread (`pipeline_executor`) and the
    consumer on the event loop, so each put goes through
    `loop.call_soon_threadsafe`: it never blocks the pipeline. Memory is bounded
    by the response, which the pipeline accumulates anyway.

    After `close()`, or once the loop is gone, puts are dropped and the pipeline
    runs to completion (PRD-015 Section 7.6's rule, D15). There is no
    end-of-stream event: `close()` only stops further puts; the end signal
    belongs to the consumer, which knows when the pipeline future finishes.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: Optional["asyncio.Queue[DeliveryEvent]"] = None,
    ) -> None:
        self._loop = loop
        self.queue: "asyncio.Queue[DeliveryEvent]" = queue if queue is not None else asyncio.Queue()
        self._closed = False

    def close(self) -> None:
        self._closed = True

    def _put(self, event: DeliveryEvent) -> None:
        if self._closed:
            return
        try:
            self._loop.call_soon_threadsafe(self.queue.put_nowait, event)
        except RuntimeError:
            # The loop is closed: the consumer is gone.
            self._closed = True

    def stage(self, name: StageName) -> None:
        self._put(StageEvent(name))

    def phase(self, name: PhaseName, action_kind: Optional[OperationKind] = None) -> None:
        self._put(PhaseEvent(name, action_kind))

    def content(self, text: str) -> None:
        self._put(ContentEvent(text))

    def reasoning(self, text: str) -> None:
        self._put(ReasoningEvent(text))

    def committed(self, completion_id: str) -> None:
        self._put(CommittedEvent(completion_id))
