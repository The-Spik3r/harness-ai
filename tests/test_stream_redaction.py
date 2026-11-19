"""PRD-021 STORY-007: the output gate and the reasoning gate (PRD-021 6.5, F5; D7, D8, Risk 1, T2).

Presidio tests on the small model (the autouse fixture of
tests/test_pii_structure_safe.py pins it too). The analyzers are built once for
the module and reused by every per-offset loop; the loops inject
`final_redact=lambda t, p: (t, [])` where they only look at what was released.

The segmenter's own tests (no Presidio) are tests/test_stream_segments.py.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import dataclasses

import pytest

import app.services.pii_redactor as pii_redactor
import app.services.stream_redaction as stream_redaction
from app.config import settings
from app.services.pii_policy import get_pii_policy
from app.services.pii_redactor import PiiRedactorError, apply_spans, redact, redact_for_policy, redaction_spans
from app.services.stream_redaction import (
    TAIL_CHARACTERS,
    OutputGate,
    gate_applies,
    reasoning_policy,
    redact_reasoning,
)
from tests import test_pii_corpus_files as corpus_files
from tests.fixtures.prd021_gate_corpus import CORPUS
from tests.test_pii_characterization import REDACT_CASES

_CHAT_ENTITIES = ("PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN", "IBAN_CODE", "LOCATION")
_CODE_ENTITIES = ("EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN", "IBAN_CODE")


@pytest.fixture(scope="module", autouse=True)
def _small_model_once():
    """Pin the settings the policies read, then build both analyzers once for the module."""
    patch = pytest.MonkeyPatch()
    patch.setattr(settings, "PII_NLP_MODEL", "en_core_web_sm")
    patch.setattr(settings, "PII_REDACTION_ENABLED", True)
    patch.setattr(settings, "PII_ENTITIES", ",".join(_CHAT_ENTITIES))
    patch.setattr(settings, "PII_SCORE_THRESHOLD", 0.35)
    patch.setattr(settings, "PII_ENTITIES_CODE", ",".join(_CODE_ENTITIES))
    patch.setattr(pii_redactor, "_analyzer", None)
    patch.setattr(pii_redactor, "_anonymizer", None)
    patch.setattr(pii_redactor, "_pattern_analyzer", None)
    pii_redactor._get_analyzer()
    pii_redactor._get_analyzer(_CODE_ENTITIES)
    yield
    patch.undo()


def _chat():
    """The `chat` policy with its fields pinned, so .env cannot move them."""
    return dataclasses.replace(get_pii_policy("chat"), entities=_CHAT_ENTITIES, threshold=0.35)


def _code(**overrides):
    """The `code` policy with the gate on (output=True) and its fields pinned."""
    fields = dict(
        entities=_CODE_ENTITIES, threshold=0.40, skip_fenced_blocks=True, structure_safe=True, output=True
    )
    fields.update(overrides)
    return dataclasses.replace(get_pii_policy("code"), **fields)


def _no_final(text, policy):
    return text, []


def _run(policy, deltas, holdback_max=400, final_redact=_no_final):
    gate = OutputGate(policy, holdback_max, final_redact=final_redact)
    out = [gate.feed(delta) for delta in deltas]
    result = gate.finish()
    return out, result


# --- the span entry point --------------------------------------------------------


@pytest.mark.parametrize("text", [case[0] for case in REDACT_CASES])
def test_chat_spans_applied_equal_redact(text):
    # PRD-021 6.5: the gate's replacement text is step 8's, byte for byte.
    assert apply_spans(text, redaction_spans(text, _chat())) == redact(text)[0]


@pytest.mark.parametrize("path", corpus_files._CODE_FILES, ids=corpus_files._ids(corpus_files._CODE_FILES))
def test_code_spans_applied_equal_redact_for_policy(path):
    text = corpus_files._read(path)
    assert apply_spans(text, redaction_spans(text, _code())) == redact_for_policy(text, _code()).text


def test_redaction_spans_are_sorted_and_disjoint():
    text = "Priya Raghunathan (priya.raghunathan@example.com, phone +1 212 555 0147) lives in Chicago."
    spans = redaction_spans(text, _chat())
    assert spans and spans == sorted(spans)
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))
    assert all(replacement == f"<{entity}>" for _, _, entity, replacement in spans)


def test_redaction_spans_off_switch_and_empty_text(monkeypatch):
    assert redaction_spans("", _chat()) == []
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
    assert redaction_spans("Jane Doe lives at jane@example.com", _chat()) == []
    assert redaction_spans("Jane Doe lives at jane@example.com", _code()) == []


# --- the gate ---------------------------------------------------------------------


def test_the_tail_keeps_only_the_last_200_raw_characters():
    gate = OutputGate(_chat(), 400, final_redact=_no_final)
    gate.feed("word " * 100 + ". ")
    gate.feed("x")
    assert len(gate._raw_tail) == TAIL_CHARACTERS == 200


@pytest.fixture
def stub_spans(monkeypatch):
    """Replace redaction_spans with a recorder returning the spans queued for each call."""
    calls, queue = [], []

    def fake(text, policy, *, analysis=None, json_mode=True):
        calls.append((text, analysis, json_mode))
        return queue.pop(0) if queue else []

    monkeypatch.setattr(pii_redactor, "redaction_spans", fake)
    return calls, queue


def test_a_span_wholly_inside_the_tail_is_ignored_and_a_crossing_span_is_clipped(stub_spans):
    calls, queue = stub_spans
    gate = OutputGate(_chat(), 400, final_redact=_no_final)
    queue.append([])
    # The terminator and its space arrived together, so the segment is released at once.
    assert gate.feed("Alpha beta. ") == "Alpha beta. "
    assert gate.released_so_far == "Alpha beta. "
    # tail = "Alpha beta. " (12 characters); the segment is "Gamma delta. ".
    queue.append([(0, 5, "E1", "<E1>"), (8, 16, "E2", "<E2>"), (18, 23, "E3", "<E3>")])
    out = gate.feed("Gamma delta. ")
    assert out == "<E2>a <E3>. "  # E1 ignored; E2 clipped to the segment ("Gamm"); E3 inside
    assert calls[1][0] == "Alpha beta. Gamma delta. "
    assert calls[1][2] is False  # json_mode off for a segment
    result = gate.finish()
    assert result.released == "Alpha beta. <E2>a <E3>. "
    assert result.diverged is True  # the final pass (stubbed to identity) differs from the release


def test_every_segment_is_redacted_before_it_is_returned(stub_spans):
    calls, queue = stub_spans
    gate = OutputGate(_chat(), 400, final_redact=_no_final)
    queue.append([(3, 6, "P", "<P>")])
    assert gate.feed("My Bob went. Next") == "My <P> went. "
    assert gate.released_so_far == "My <P> went. "
    result = gate.finish()
    assert result.remainder == "Next" and result.released == "My <P> went. Next"


def test_feed_empty_and_finish_twice():
    gate = OutputGate(_chat(), 400, final_redact=_no_final)
    assert gate.feed("") == ""
    gate.finish()
    with pytest.raises(RuntimeError, match="already finished"):
        gate.finish()


@pytest.mark.parametrize("entity,text,raw", CORPUS, ids=[row[0] for row in CORPUS])
def test_corpus_precondition_the_small_model_masks_every_entity(entity, text, raw):
    assert raw in text and len(text) <= 90
    masked, entities = redact(text)
    assert raw not in masked and entity in entities


@pytest.mark.parametrize("entity,text,raw", CORPUS, ids=[row[0] for row in CORPUS])
def test_no_divergence_when_no_entity_crosses_a_boundary_under_chat(entity, text, raw):
    # Real final_redact: replacement text byte-equal to step 8's.
    for deltas in ([text], [text[:30], text[30:]], list(text)):
        out, result = _run(_chat(), deltas, final_redact=redact_for_policy)
        assert raw not in result.released
        assert result.diverged is False and result.released == result.final_text
        assert "".join(out) + result.remainder == result.released


@pytest.mark.parametrize(
    "entity,text,raw", [row for row in CORPUS if row[0] in _CODE_ENTITIES], ids=[r[0] for r in CORPUS if r[0] in _CODE_ENTITIES]
)
def test_no_divergence_under_code_with_the_five_code_entities(entity, text, raw):
    text = text.replace(". ", ".\n", 1)  # `code` cuts at newlines
    out, result = _run(_code(), [text[:25], text[25:]], final_redact=redact_for_policy)
    assert raw not in result.released
    assert result.diverged is False and result.released == result.final_text


@pytest.mark.parametrize("entity,text,raw", CORPUS, ids=[row[0] for row in CORPUS])
def test_t2_no_raw_entity_is_released_at_any_delta_offset(entity, text, raw):
    # T2: whatever the delta boundary, the entity never leaves raw.
    assert raw in text and raw not in redact(text)[0]  # the precondition, so the loop cannot pass vacuously
    runs = 0
    for offset in range(len(text) + 1):
        out, result = _run(_chat(), [text[:offset], text[offset:]])
        assert raw not in result.released, (entity, offset)
        runs += 1
    assert runs == len(text) + 1


def test_a_forced_cut_inside_a_multi_word_entity_is_clipped_and_the_final_pass_flags_it():
    # Orchestrator decision (3.2): the head already released cannot be recalled,
    # but its continuation is masked rather than leaked, and diverged is True.
    text = "Payment info follows. Wire it to IBAN GB82 WEST 1234 5698 7654 32 please."
    out, result = _run(_chat(), [text], holdback_max=34, final_redact=redact_for_policy)
    assert "1234 5698 7654 32" not in result.released  # the continuation is masked
    assert "<IBAN_CODE>" in result.released
    assert "GB82 WEST" in result.released  # the unrecallable head: the measured residual
    assert result.diverged is True
    assert "GB82" not in result.final_text and "<IBAN_CODE>" in result.final_text


def test_risk_1_a_cut_inside_an_unbroken_entity_may_leak_and_the_final_pass_detects_it():
    # holdback_max below the entity length and no whitespace in it: the head leaks (Risk 1),
    # and finish() reports it. Not an xfail: it asserts that detection works.
    text = "Write to priya.raghunathan@example.com now."
    out, result = _run(_chat(), [text], holdback_max=10, final_redact=redact_for_policy)
    assert result.released != result.final_text
    assert result.diverged is True
    assert "@example.com" not in result.final_text


def test_a_tail_context_word_still_helps_across_a_boundary():
    # "phone number" ends one segment's sentence; the number opens the next line: the tail's context counts.
    text = "My phone number is\n+1 415 555 0134 for urgent cases."
    out, result = _run(_chat(), [text], final_redact=redact_for_policy)
    assert "555 0134" not in result.released


# --- fences ------------------------------------------------------------------------

_FENCED = "```py\nemail a@b.com\n```\n"


def test_fenced_lines_pass_unredacted_and_prose_is_masked():
    text = "Mail jane.roe@example.com first.\n" + _FENCED + "Then jane.roe@example.com again.\n"
    out, result = _run(_code(), [text], final_redact=redact_for_policy)
    assert _FENCED in result.released  # the fenced block, byte for byte
    assert result.released.count("<EMAIL_ADDRESS>") == 2
    assert result.diverged is False


def test_a_fence_opener_split_at_every_offset_is_seen_whole():
    text = "intro\n" + _FENCED + "outro a@b.com\n"
    expected = _run(_code(), [text], final_redact=redact_for_policy)[1].released
    for offset in range(len(text) + 1):
        _, result = _run(_code(), [text[:offset], text[offset:]], final_redact=redact_for_policy)
        assert result.released == expected and result.diverged is False, offset
    assert "email a@b.com" in expected and "outro <EMAIL_ADDRESS>" in expected


def test_gate_applies():
    assert gate_applies(_chat(), True) is True
    assert gate_applies(_code(output=False), True) is False  # `code` with output off has no gate
    assert gate_applies(_code(), True) is True
    assert gate_applies(_chat(), False) is False  # the master switch


# --- failure -----------------------------------------------------------------------


class _FailingAfter:
    """An analyzer that works for `ok` calls, then raises."""

    def __init__(self, real, ok):
        self.real, self.ok = real, ok

    def analyze(self, **kwargs):
        if self.ok <= 0:
            raise RuntimeError("boom")
        self.ok -= 1
        return self.real.analyze(**kwargs)


def test_a_redactor_error_poisons_the_gate_and_releases_nothing_raw(monkeypatch):
    real = pii_redactor._get_analyzer()
    fake = _FailingAfter(real, ok=1)
    monkeypatch.setattr(pii_redactor, "_get_analyzer", lambda entities=None: fake)
    gate = OutputGate(_chat(), 400, final_redact=_no_final)
    with pytest.raises(PiiRedactorError) as caught:
        gate.feed("First sentence. Second jane@example.com sentence. ")
    assert "jane@example.com" not in str(caught.value)  # T9: no content in the message
    assert gate.released_so_far == ""  # the first segment of the failed call was discarded
    with pytest.raises(PiiRedactorError):
        gate.feed("more")
    with pytest.raises(PiiRedactorError):
        gate.finish()


# --- reasoning ---------------------------------------------------------------------


def test_reasoning_policy_is_chat_whatever_the_content_policy():
    chat = _chat()
    policy = reasoning_policy(_code(output=False))
    assert policy.output is True and policy.structure_safe is False and policy.skip_fenced_blocks is False
    assert set(chat.entities) <= set(policy.entities)
    assert reasoning_policy(policy) == policy  # idempotent
    assert reasoning_policy(get_pii_policy("chat")).name == "chat"


def test_reasoning_policy_keeps_an_extra_entity_the_content_policy_masks():
    policy = reasoning_policy(_code(entities=_CODE_ENTITIES + ("DATE_TIME",)))
    assert "DATE_TIME" in policy.entities and set(_CHAT_ENTITIES) <= set(policy.entities)
    assert reasoning_policy(policy) == policy


def test_redact_reasoning_masks_what_code_would_not_and_ignores_output_off():
    text = "I should tell Dr. Maria Lopez in Seattle about this."
    code = _code(output=False)
    assert redact_for_policy(text, code).text == text  # no NER under `code`
    result = redact_reasoning(text, code)
    assert "Maria Lopez" not in result.text and "Seattle" not in result.text
    assert {"PERSON", "LOCATION"} <= set(result.entities)


def test_redact_reasoning_off_when_the_master_switch_is_off(monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
    text = "Contact jane@example.com"
    assert redact_reasoning(text, _code()) == (text, [])


def test_the_reasoning_gate_uses_chat_boundaries_and_matches_its_final_pass():
    policy = reasoning_policy(_code(output=False))
    text = (
        "First I consider the request. The user, Maria Lopez, wants a summary. "
        "She writes from Seattle! Then I answer.\nDone."
    )
    out, result = _run(policy, [text[:40], text[40:]], 400, final_redact=redact_reasoning)
    assert "Maria Lopez" not in result.released and "Seattle" not in result.released
    assert result.diverged is False
    assert len([piece for piece in out if piece]) >= 1


def test_stream_redaction_has_no_logging_import():
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path(stream_redaction.__file__).read_text(encoding="utf-8"))
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert "logging" not in names
