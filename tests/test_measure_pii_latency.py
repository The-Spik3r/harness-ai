"""PRD-012 STORY-003: the pure parts of scripts/measure_pii_latency.py, and drift guards.

The script is a spike that records numbers and asserts none; nothing here times
anything or loads en_core_web_lg. What is tested is what the numbers depend on:
the conversation is exactly the size it claims, the false-positive classifier
follows the corpus's value classes (tests/corpora/pii/SOURCES.md), p95 is
nearest-rank, chunks are line-aligned, the corpus copies the script keeps have
not drifted from this test tree's, and the tokenizer-only engine's lemma
component is what restores Presidio's context boost (plan F-2) -- the mechanism
STORY-006 carries into app/.
"""

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

import scripts.measure_pii_latency as bench
from tests import test_pii_corpus_files as corpus_files

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_importing_the_script_builds_no_analyzer():
    """In a fresh interpreter: in this one, other tests build and reset the singleton."""
    probe = (
        "import scripts.measure_pii_latency\n"
        "from app.services import pii_redactor\n"
        "assert pii_redactor._analyzer is None, pii_redactor._analyzer\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe], cwd=_REPO_ROOT, capture_output=True, text=True, timeout=120
    )
    assert completed.returncode == 0, completed.stderr


# --- the conversation ---


@pytest.mark.parametrize("size", [40_000, 200_000, 400_000, 12_345])
def test_conversation_is_exactly_the_requested_size(size):
    conversation = bench._conversation(size)

    assert sum(len(m.content) for m in conversation) == size
    assert conversation[0].role == "system"
    assert {m.role for m in conversation[1:]} <= {"user", "assistant"}  # step 0 refuses `tool`


def test_conversation_smaller_than_the_system_prompt_is_one_truncated_system_turn():
    conversation = bench._conversation(100)

    assert [m.role for m in conversation] == ["system"]
    assert len(conversation[0].content) == 100


def test_conversation_is_deterministic():
    assert bench._conversation(50_000) == bench._conversation(50_000)


def test_assistant_turns_carry_a_fenced_excerpt_and_the_shape_counts_it():
    conversation, shape = bench._build(200_000)

    assistants = [m for m in conversation if m.role == "assistant"]
    assert assistants and all(bench._FENCE in m.content for m in assistants)
    assert 0 < shape.fenced_characters < 200_000
    assert shape.messages == len(conversation)
    assert shape.largest == max(len(m.content) for m in conversation)


def test_single_message_worst_case_is_one_user_turn_of_the_same_size():
    message = bench._single_message(200_000)

    assert [m.role for m in message] == ["user"]
    assert len(message[0].content) == 200_000


# --- the false-positive classifier ---


@pytest.mark.parametrize(
    "entity,span,expected",
    [
        ("EMAIL_ADDRESS", "Jane.Doe@Example.com", True),  # mixed case, plan F-5
        ("EMAIL_ADDRESS", "ops@example.org", True),
        ("EMAIL_ADDRESS", "maria.lopez@corp.com", False),  # not a reserved domain
        ("PHONE_NUMBER", "+1 415 555 0134", True),
        ("PHONE_NUMBER", "(212) 555-0147", True),
        ("PHONE_NUMBER", "14155550134", True),
        ("PHONE_NUMBER", "078-05-1120", False),  # the voided SSN, a deliberate near-miss
        ("PHONE_NUMBER", "415-555-0342", False),  # 555 but outside 0100-0199
        ("CREDIT_CARD", "4111 1111 1111 1111", True),
        ("CREDIT_CARD", "4242 4242 4242 4242", False),
        ("IBAN_CODE", "GB82 WEST 1234 5698 7654 32", True),
        ("IBAN_CODE", "de89370400440532013000", True),
        ("US_SSN", "219-09-9999", True),
        ("US_SSN", "078-05-1120", False),
        ("PERSON", "Patrick O''Brien'", True),  # SQL-escaped, trailing quote stripped
        ("PERSON", "Patrick O\\'Brien", True),
        ("PERSON", "Maria", True),
        ("PERSON", "Tomás Herrera", True),
        ("PERSON", "ping Priya Raghunathan", False),  # the span swallowed a word
        ("PERSON", 'display_name="Patrick O\\\'Brien', False),  # the span swallowed code
        ("PERSON", "PENDING_VERIFICATION", False),
        ("LOCATION", "San Francisco", True),
        ("LOCATION", "USD", False),
        ("LOCATION", "Europe/Berlin", False),
        ("CRYPTO", "anything", False),  # a type the corpus has no value class for
    ],
)
def test_true_positive_classification(entity, span, expected):
    assert bench._is_true_positive(entity, span) is expected


@pytest.mark.parametrize(
    "span,expected",
    [('"Jane Doe"', True), ("O'Brien", True), ("a\\b", True), ("a\nb", True), ("`x`", True), ("Jane Doe", False)],
)
def test_structural_spans(span, expected):
    assert bench._is_structural(span) is expected


# --- timing helpers ---


def test_nearest_rank_p95():
    twenty = bench.Samples("x")
    for value in range(1, 21):
        twenty.add(float(value))
    one = bench.Samples("y")
    one.add(7.0)

    assert twenty.summary() == (1.0, 10.5, 19.0)
    assert one.summary() == (7.0, 7.0, 7.0)


def test_chunks_are_line_aligned_and_cover_the_text():
    text = "".join(f"line {i:05d} {'x' * (i % 50)}\n" for i in range(3000))

    chunks = bench._chunks(text, 20_000)

    assert "".join(chunk for _, chunk in chunks) == text
    assert [offset for offset, _ in chunks] == [sum(len(c) for _, c in chunks[:i]) for i in range(len(chunks))]
    assert all(len(chunk) <= 20_000 and chunk.endswith("\n") for _, chunk in chunks)


def test_a_line_longer_than_the_window_is_cut_hard():
    chunks = bench._chunks("y" * 45_000, 20_000)

    assert [len(chunk) for _, chunk in chunks] == [20_000, 20_000, 5_000]


# --- decision rules ---


def test_rule_r2_doubles_and_rounds_up_to_250_ms():
    assert bench._rule_r2(430.0) == 1000
    assert bench._rule_r2(500.0) == 1000
    assert bench._rule_r2(501.0) == 1250
    assert bench._rule_r2(None) is None


def test_interpolated_size_is_log_log_and_rounded_down():
    points = [(100_000, 500.0), (200_000, 2000.0)]  # p95 ~ size^2

    assert bench._interpolated_size(points, 1000.0) == 140_000  # sqrt(2) * 100k = 141,421
    assert bench._interpolated_size(points, 400.0) is None
    assert bench._interpolated_size(points, 5000.0) == 200_000


def _row(threshold, prose=6, probes=2, fp=0):
    return bench.ThresholdRow(threshold, fp, 0, prose, 6, [], probes, 2, 0, 0, 0)


def test_rule_r1_takes_the_highest_acceptable_threshold():
    rows = [_row(0.35, fp=5), _row(0.40, fp=5), _row(0.50, probes=0, fp=1)]

    threshold, note = bench._rule_r1(rows)

    assert threshold == 0.40
    assert "0.50" in note


def test_rule_r1_reports_when_nothing_is_acceptable():
    assert bench._rule_r1([_row(0.35, prose=5)])[0] is None


def test_rule_r3_branches():
    assert bench._rule_r3(1000, {200_000: 900.0}, {200_000: 800.0})[0] == 200_000
    limit, note = bench._rule_r3(1000, {200_000: 2000.0}, {200_000: 900.0})
    assert limit == 200_000 and "chunks" in note
    limit, note = bench._rule_r3(1000, {100_000: 500.0, 200_000: 2000.0}, {200_000: 1500.0})
    assert limit == 140_000 and "refuses" in note


# --- drift guards against this test tree ---


def test_the_cast_matches_the_corpus_loader():
    assert bench._CAST == corpus_files._CAST


def test_corpus_discovery_matches_the_corpus_loader():
    assert bench._corpus("code") == corpus_files._CODE_FILES
    assert bench._corpus("prose") == corpus_files._PROSE_FILES
    assert bench._corpus("json") == corpus_files._JSON_FILES


def test_declared_headers_match_the_corpus_loader():
    for path in corpus_files._PROSE_FILES:
        assert bench._declared(path) == corpus_files._declared(path)


def test_pattern_entities_are_known_and_contain_no_ner_type():
    assert set(bench.PATTERN_ENTITIES) <= corpus_files._KNOWN_ENTITIES
    assert not set(bench.PATTERN_ENTITIES) & corpus_files._NER_ENTITIES
    assert bench.NER_ENTITIES == corpus_files._NER_ENTITIES


# --- the tokenizer-only engine (plan F-1, F-2) ---


def _phone_score(analyzer, text):
    results = analyzer.analyze(text=text, language="en", entities=["PHONE_NUMBER"], score_threshold=0)
    assert len(results) == 1
    return round(results[0].score, 2)


def test_tokenizer_only_route_with_lemmas_boosts_context():
    with_lemmas = bench._subclass_analyzer(lemmas=True)
    without = bench._subclass_analyzer(lemmas=False)

    assert with_lemmas.nlp_engine.nlp["en"].pipe_names == ["lower_as_lemma"]
    assert _phone_score(with_lemmas, "My phone is 415-555-0134 please.") == 0.75
    assert _phone_score(without, "My phone is 415-555-0134 please.") == 0.40
    assert _phone_score(with_lemmas, "Call 415-555-0134") == 0.40  # `call` is not a context word


def test_blank_route_by_name_never_downloads(monkeypatch):
    calls = []
    monkeypatch.setattr(bench.spacy.cli, "download", lambda *a, **k: calls.append(a))

    route = bench._attempt("provider:blank:en", lambda: bench._provider_analyzer("blank:en"))

    assert not route.loaded
    assert "refused" in route.error
    assert calls == []  # the guard replaced the patched function too: nothing reached a download
    assert bench.spacy.cli.download is not None


def test_a_route_raising_systemexit_is_recorded_not_fatal():
    def exits():
        raise SystemExit(1)

    route = bench._attempt("exits", exits)

    assert (route.loaded, route.error) == (False, "SystemExit: 1")


def test_route_choice_prefers_fewest_differences():
    routes = [
        bench.Route("a", False, "boom"),
        bench.Route("b", True, None, parity=bench.Parity(17, 140, ())),
        bench.Route("c", True, None, parity=bench.Parity(17, 4, ())),
    ]

    assert bench._pattern_blank_route(routes).name == "c"
    assert bench._pattern_blank_route(routes[:1]) is None
