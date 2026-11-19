"""Hold-back redaction of a streamed reply and of reasoning (PRD-021 Sections 6.5, F5; D7, D8, Risk 1).

Two halves. The top one is the `Segmenter`: pure text segmenting (sentence
and line boundaries, a forced cut at `holdback_max`, fence tracking), with no
Presidio and no policy object. The bottom one is `OutputGate`, which redacts
each released segment with `pii_redactor.redaction_spans` over `tail + segment`
and keeps only the spans that reach into the segment, so context before the
boundary helps the analyzer and nothing already released is touched twice.

The gate redacts a segment *before* it leaves, so it can be wrong in exactly
one way: an entity longer than the hold-back, or cut by a forced cut, may be
released in two pieces. Step 8's whole-reply pass (`final_redact`) stays
authoritative: `finish()` runs it once and reports `diverged` when what was
released differs from it (Risk 1, T2). The caller decides what a divergence
means (STORY-008: the committed row and the `final` frame carry the final text).

Pure of settings and I/O: no `app.config` import, no logging, no network. The
caller passes `holdback_max` in. No message here names content: a failure
raises `PiiRedactorError` without text (T9).
"""

import dataclasses
import re
from typing import Callable, Literal, Optional

from app.services import pii_redactor
from app.services.pii_policy import PiiPolicy, get_pii_policy

#: Raw characters of already-released text kept as context for the next
#: segment (PRD-021 6.5). Not configurable: it only has to cover the words an
#: entity's context depends on ("my phone number is ...").
TAIL_CHARACTERS = 200

# --- Segmenter: pure --------------------------------------------------------

#: Copies of pattern_detector's fence regexes (`_FENCE_OPEN` and the closer
#: built in `strip_fenced_blocks`); the differential test in
#: tests/test_stream_segments.py pins them to it. Not imported: private names.
_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})[^\n]*$", re.MULTILINE)
_SENTENCE_END = ".?!…"


@dataclasses.dataclass(frozen=True)
class Segment:
    """One releasable piece of the reply. `fenced`: it sits inside a fenced block (or is a fence line)."""

    text: str
    fenced: bool


def _closer(delimiter: str) -> "re.Pattern[str]":
    return re.compile(r"^ {0,3}" + re.escape(delimiter[0]) + r"{%d,}[ \t]*$" % len(delimiter), re.MULTILINE)


class Segmenter:
    """Cuts a stream of text deltas into segments (PRD-021 6.5). Pure; no Presidio.

    - `chat`: a segment ends after the first `.`, `?`, `!` or `...` that is
      followed by whitespace (the whitespace is included; a terminator at the
      end of the buffer waits for the next character, so `3.5` and `a.b.c`
      never cut), or after the first newline, whichever comes first.
    - `code`: a segment ends after each newline.
    - Both: a segment is never longer than `holdback_max`. When no boundary
      falls within it, the cut is after the last whitespace of the first
      `holdback_max` characters, or exactly at `holdback_max` without one.
      The cut depends only on those characters, so it is the same however the
      deltas were split.
    - With `skip_fenced` (`code` only) every line is classified as fenced or
      not, as strip_fenced_blocks() does: opener line and closer line are
      fenced, and an unterminated fence runs to the end. A line is classified
      when its end arrives, so an opener split across deltas is seen whole. A
      line cut by `holdback_max` is classified from its head and can no longer
      be a closer (a documented limit: a closer is a short line).
    """

    def __init__(self, kind: Literal["chat", "code"], holdback_max: int, skip_fenced: bool = False) -> None:
        if holdback_max < 1:
            raise ValueError("holdback_max must be at least 1")
        self._kind = kind
        self._max = holdback_max
        self._track = skip_fenced and kind == "code"
        self._buffer = ""
        self._fence: Optional[tuple[str, re.Pattern]] = None  # (delimiter, closer regex) while inside a fence
        self._line_fenced: Optional[bool] = None  # classification of a line already partly released

    def push(self, text: str) -> list[Segment]:
        """Add a delta; the segments that are now complete, in order."""
        self._buffer += text
        out: list[Segment] = []
        while self._buffer:
            cut = self._boundary()
            if cut is None or cut > self._max:
                if len(self._buffer) <= self._max:
                    break
                cut = self._forced_cut()
            out.append(self._take(cut))
        return out

    def flush(self) -> list[Segment]:
        """End of stream: the held remainder, as the last segment(s)."""
        out = self.push("")
        if self._buffer:
            out.append(self._take(len(self._buffer)))
        return out

    def _boundary(self) -> Optional[int]:
        buffer = self._buffer
        for index, char in enumerate(buffer):
            if char == "\n":
                return index + 1
            if self._kind == "chat" and char in _SENTENCE_END and index + 1 < len(buffer) and buffer[index + 1].isspace():
                return index + 2
        return None

    def _forced_cut(self) -> int:
        window = self._buffer[: self._max]
        for index in range(len(window) - 1, 0, -1):
            if window[index].isspace():
                return index + 1
        return self._max

    def _take(self, cut: int) -> Segment:
        text, self._buffer = self._buffer[:cut], self._buffer[cut:]
        if not self._track:
            return Segment(text, False)
        ends_line = text.endswith("\n") or not self._buffer
        if self._line_fenced is not None:  # the rest of a line cut earlier
            fenced = self._line_fenced
            if ends_line:
                self._line_fenced = None
            return Segment(text, fenced)
        fenced = self._classify(text[:-1] if text.endswith("\n") else text, whole_line=ends_line)
        if not ends_line:
            self._line_fenced = fenced
        return Segment(text, fenced)

    def _classify(self, line: str, whole_line: bool) -> bool:
        if self._fence is not None:
            if whole_line and self._fence[1].match(line):
                self._fence = None
            return True
        opening = _OPEN.match(line)
        if opening is None:
            return False
        delimiter = opening.group(1)
        self._fence = (delimiter, _closer(delimiter))
        return True


# --- Gate: redacts through pii_redactor --------------------------------------

@dataclasses.dataclass(frozen=True)
class GateResult:
    """What `OutputGate.finish()` reports (PRD-021 6.5, Risk 1).

    `released` is everything `feed()` and `finish()` returned, and `remainder`
    the part of it `finish()` itself released (the held tail of the stream: the
    caller sends it as the last delta). `final_text` and `final_entities` are
    the single whole-reply pass's (step 8's), and `diverged` is
    `released != final_text`: the gate let through something the final pass
    would have masked, or masked something it would not have.
    """

    released: str
    final_text: str
    final_entities: list[str]
    diverged: bool
    remainder: str = ""


def _blank(text: str) -> str:
    """What strip_fenced_blocks() makes of fenced text: every non-newline character a newline."""
    return re.sub(r"[^\n]", "\n", text)


class OutputGate:
    """Redacts a streamed reply segment by segment (PRD-021 6.5).

    `feed(text)` returns the text that may leave now (possibly ""), `finish()`
    the last of it plus a `GateResult`. Each non-fenced segment is analyzed as
    `tail + segment` (the last `TAIL_CHARACTERS` raw characters released) and
    only the spans reaching into the segment are applied:

    - a span wholly inside the tail is ignored (it was released already);
    - a span that starts in the tail and ends inside the segment is *clipped*
      to the segment and masked with its replacement. The head of the entity
      cannot be recalled, but its continuation is masked rather than leaked;
      the release then differs from the final pass and `diverged` is True.

    Fenced segments (`code` with `skip_fenced_blocks`) pass unredacted and only
    feed the tail, like step 8's fence blanking. `json_mode` is off: a segment
    is never the document step 8 would test, so a reply that is one JSON
    document can diverge, and the final pass is authoritative.

    A `PiiRedactorError` from any call propagates and poisons the gate: nothing
    redacted in the failed call is returned, nothing is ever released raw, and
    later calls re-raise. Reads no settings, logs nothing.
    """

    def __init__(
        self,
        policy: PiiPolicy,
        holdback_max: int,
        *,
        final_redact: Callable[[str, PiiPolicy], tuple] = pii_redactor.redact_for_policy,
    ) -> None:
        self._policy = policy
        self._final_redact = final_redact
        self._segmenter = Segmenter(
            "code" if policy.structure_safe else "chat",
            holdback_max,
            policy.skip_fenced_blocks and policy.structure_safe,
        )
        self._raw_tail = ""
        self._analysis_tail = ""
        self._raw: list[str] = []
        self._released: list[str] = []
        self._poisoned = False
        self._finished = False

    @property
    def released_so_far(self) -> str:
        """Everything returned so far (STORY-008's charge for a mid-stream fault)."""
        return "".join(self._released)

    def feed(self, text: str) -> str:
        """Add a delta of the raw reply; the text that may be released now."""
        self._check_usable()
        if not text:
            return ""
        self._raw.append(text)
        return self._release(lambda: self._segmenter.push(text))

    def finish(self) -> GateResult:
        """End of stream: release the remainder and run the final pass once."""
        self._check_usable()
        remainder = self._release(self._segmenter.flush)
        self._finished = True
        final_text, final_entities = self._final_redact("".join(self._raw), self._policy)
        released = self.released_so_far
        return GateResult(released, final_text, list(final_entities), released != final_text, remainder)

    # -- internals -------------------------------------------------------

    def _check_usable(self) -> None:
        if self._finished:
            raise RuntimeError("OutputGate already finished")
        if self._poisoned:
            raise pii_redactor.PiiRedactorError("output gate failed earlier; nothing more is released")

    def _release(self, make_segments: Callable[[], list[Segment]]) -> str:
        try:
            out = "".join(self._redact_segment(segment) for segment in make_segments())
        except pii_redactor.PiiRedactorError:
            self._poisoned = True
            raise
        self._released.append(out)
        return out

    def _redact_segment(self, segment: Segment) -> str:
        if segment.fenced:
            out = segment.text
            analysis = _blank(segment.text)
        else:
            raw = self._raw_tail + segment.text
            analysis = self._analysis_tail + segment.text
            spans = pii_redactor.redaction_spans(raw, self._policy, analysis=analysis, json_mode=False)
            tail = len(self._raw_tail)
            shifted = [
                (max(start, tail) - tail, end - tail, entity, replacement)
                for start, end, entity, replacement in spans
                if end > tail
            ]
            out = pii_redactor.apply_spans(segment.text, shifted)
            analysis = segment.text
        self._raw_tail = (self._raw_tail + segment.text)[-TAIL_CHARACTERS:]
        self._analysis_tail = (self._analysis_tail + analysis)[-TAIL_CHARACTERS:]
        return out


# --- Policy helpers ----------------------------------------------------------


def gate_applies(policy: PiiPolicy, redaction_enabled: bool) -> bool:
    """Whether the content gate runs: the master switch is on and the policy redacts output (`code` may not)."""
    return redaction_enabled and policy.output


def reasoning_policy(policy: PiiPolicy) -> PiiPolicy:
    """The policy reasoning is redacted under (PRD-021 D8): `chat`, whatever the request's policy.

    Reasoning is prose shown to a person, so it is masked as `chat` masks it,
    plus any entity type the request's own list adds, so no entity the content
    policy masks is dropped. Idempotent. The master switch still turns it off,
    as it turns off all redaction (PRD-012).
    """
    chat = get_pii_policy("chat")
    extra = tuple(entity for entity in policy.entities if entity not in chat.entities)
    if not extra:
        return chat
    return dataclasses.replace(chat, entities=chat.entities + extra)


def redact_reasoning(text: str, policy: PiiPolicy) -> pii_redactor.RedactionResult:
    """Mask reasoning text under `reasoning_policy(policy)`, ignoring `policy.output`.

    Shaped like `redact_for_policy` so STORY-008 can pass it as the gate's
    `final_redact` for the reasoning gate.
    """
    spans = pii_redactor.redaction_spans(text, reasoning_policy(policy))
    return pii_redactor.RedactionResult(
        pii_redactor.apply_spans(text, spans), sorted({entity for _, _, entity, _ in spans})
    )
