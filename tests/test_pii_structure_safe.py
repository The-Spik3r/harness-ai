"""PRD-012 STORY-008: redact_for_policy -- fence skipping, structure-safe
replacement, JSON-aware mode (PRD Sections 6.5, 6.6; F7).

- AC 1 (fences) and AC 3 (JSON) run on the real tokenizer-only analyzer the
  default `code` entities select. It loads no model.
- AC 2 (structure-safe splitting), the overlap rule and AC 4 (the JSON
  post-condition) use a stub analyzer, so each case pins one rule and does not
  depend on recognizer scores. Stub texts stay under 20,000 characters, so the
  stub sees one window, at offset 0.
- AC 5 is parametrized over tests/test_pii_characterization.py's
  REDACT_CASES, imported and not copied.

The corpus round-trip suite (`ast.parse`, prose masking) and the latency
budget are STORY-013's. This module checks the structural invariants over the
corpora that AC 2 and AC 3 name.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import dataclasses
import json

import pytest
from presidio_analyzer import RecognizerResult

import app.services.pii_redactor as pii_redactor
import scripts.measure_pii_latency as bench
from app.config import settings
from app.services.pattern_detector import strip_fenced_blocks
from app.services.pii_policy import get_pii_policy
from app.services.pii_redactor import PiiRedactorError, RedactionResult, redact, redact_for_policy
from tests import test_pii_corpus_files as corpus_files
from tests.test_pii_characterization import REDACT_CASES

_CODE_ENTITIES = ["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN", "IBAN_CODE"]
_BACKSLASH = "\\"


@pytest.fixture(autouse=True)
def _small_model_and_reset(monkeypatch):
    monkeypatch.setattr(settings, "PII_NLP_MODEL", "en_core_web_sm")
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", True)
    # Pinned so a developer's .env cannot change which analyzer load() selects.
    monkeypatch.setattr(settings, "PII_ENTITIES_CODE", ",".join(_CODE_ENTITIES))
    monkeypatch.setattr(pii_redactor, "_analyzer", None)
    monkeypatch.setattr(pii_redactor, "_anonymizer", None)
    monkeypatch.setattr(pii_redactor, "_pattern_analyzer", None)
    yield


def _code(**overrides):
    """The `code` policy with its fields pinned, so .env cannot move them."""
    fields = dict(
        entities=tuple(_CODE_ENTITIES), threshold=0.40, skip_fenced_blocks=True, structure_safe=True
    )
    fields.update(overrides)
    return dataclasses.replace(get_pii_policy("code"), **fields)


class _StubAnalyzer:
    def __init__(self, spans):
        self.spans = spans

    def analyze(self, **kwargs):
        return [RecognizerResult(entity, start, end, 1.0) for entity, start, end in self.spans]


def _stub(monkeypatch, *spans):
    """Make every analyzer the stub, whatever entity list selects it."""
    stub = _StubAnalyzer(list(spans))
    monkeypatch.setattr(pii_redactor, "_get_analyzer", lambda entities=None: stub)
    return stub


def _span(text, needle, entity, occurrence=0):
    start = -1
    for _ in range(occurrence + 1):
        start = text.index(needle, start + 1)
    return entity, start, start + len(needle)


def _stub_redact(monkeypatch, text, needle, entity="EMAIL_ADDRESS", policy=None):
    _stub(monkeypatch, _span(text, needle, entity))
    return redact_for_policy(text, policy or _code())


class _Tripwire:
    """Stands in for the full analyzer: any attribute access is recorded and fails."""

    def __init__(self, log):
        object.__setattr__(self, "_log", log)

    def __getattr__(self, name):
        self._log.append(name)
        raise AssertionError(f"the full analyzer was reached: .{name}")


# --- AC 1: fenced blocks skipped, inline spans masked ------------------------


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_fenced_email_is_unchanged_and_prose_email_is_masked(fence):
    text = f'Send it to maria.lopez@corp.com.\n{fence}py\nOWNER = "jane.doe@example.com"\n{fence}\nThanks.'

    result = redact_for_policy(text, _code())

    assert result == RedactionResult(
        f'Send it to <EMAIL_ADDRESS>.\n{fence}py\nOWNER = "jane.doe@example.com"\n{fence}\nThanks.',
        ["EMAIL_ADDRESS"],
    )


def test_inline_backtick_email_is_masked():
    assert redact_for_policy("Ping `ops@example.org` today.", _code()).text == "Ping `<EMAIL_ADDRESS>` today."


def test_unterminated_fence_skips_to_the_end():
    text = "Owner is alice@corp.com.\n```yaml\nowner: jane@example.com\nbackup: bob@example.com\n"

    result = redact_for_policy(text, _code())

    assert result.text == "Owner is <EMAIL_ADDRESS>.\n```yaml\nowner: jane@example.com\nbackup: bob@example.com\n"


def test_fences_are_analyzed_when_skip_is_off():
    text = '```py\nOWNER = "jane.doe@example.com"\n```\n'

    result = redact_for_policy(text, _code(skip_fenced_blocks=False))

    assert result.text == '```py\nOWNER = "<EMAIL_ADDRESS>"\n```\n'


def test_fence_guard_never_touches_fenced_bytes(monkeypatch):
    """P6c: whatever the analyzer returns, fenced characters are structural."""
    text = "Mail jane@x.io\n```\nbob@y.io\n```\n"
    _stub(monkeypatch, ("EMAIL_ADDRESS", 5, text.index("```\n", 20)))

    result = redact_for_policy(text, _code())

    assert result.text == "Mail <EMAIL_ADDRESS>\n```\nbob@y.io\n```\n"


@pytest.mark.parametrize("path", corpus_files._CODE_FILES, ids=corpus_files._ids(corpus_files._CODE_FILES))
def test_code_corpus_fenced_regions_are_byte_identical(path):
    text = corpus_files._read(path)
    blanked = strip_fenced_blocks(text)

    result = redact_for_policy(text, _code()).text

    fenced = [i for i in range(len(text)) if blanked[i] != text[i]]
    # Nothing inside a fence changed, so the output has the same fence layout
    # and the same fenced characters, now shifted by the prose edits before them.
    result_blanked = strip_fenced_blocks(result)
    assert [c for i, c in enumerate(result) if result_blanked[i] != c] == [text[i] for i in fenced]


def test_the_code_corpus_has_fenced_content():
    """Guards the test above against passing vacuously."""
    assert any(strip_fenced_blocks(t) != t for t in map(corpus_files._read, corpus_files._CODE_FILES))


# --- AC 2: structure-safe splitting ------------------------------------------


def test_span_including_its_quotes_keeps_both_quotes(monkeypatch):
    text = 'owner = "jane@example.com"'

    assert _stub_redact(monkeypatch, text, '"jane@example.com"').text == 'owner = "<EMAIL_ADDRESS>"'


def test_span_across_a_line_break_is_split(monkeypatch):
    assert _stub_redact(monkeypatch, "Jane\nDoe", "Jane\nDoe", "PERSON").text == "<PERSON>\n<PERSON>"


def test_span_across_a_carriage_return_line_break_is_split(monkeypatch):
    assert _stub_redact(monkeypatch, "Jane\r\nDoe", "Jane\r\nDoe", "PERSON").text == "<PERSON>\r\n<PERSON>"


def test_span_across_a_backtick_is_split(monkeypatch):
    assert _stub_redact(monkeypatch, "jane`doe", "jane`doe", "PERSON").text == "<PERSON>`<PERSON>"


def test_span_containing_a_backslash_keeps_it(monkeypatch):
    text = r"path C:\jane\notes"

    result = _stub_redact(monkeypatch, text, r"C:\jane\notes", "PERSON")

    # `\j` and `\n` are escape units (P6b); the runs `C:`, `ane` and `otes` are masked around them.
    assert result.text == r"path <PERSON>\j<PERSON>\n<PERSON>"
    assert result.text.count(_BACKSLASH) == text.count(_BACKSLASH)


@pytest.mark.parametrize(
    "escape",
    [r"\n", r"\"", r"\\", r"\u00e9", r"\x41", r"\t"],
    ids=["newline", "quote", "backslash", "unicode", "hex", "tab"],
)
def test_escape_sequence_is_kept_whole(monkeypatch, escape):
    """F-5: an escape is structural as a whole, so a placeholder never follows a
    lone backslash (`\\<PERSON>` is an invalid escape in JSON and Java)."""
    text = f'String s = "Jane{escape}Doe";'

    result = _stub_redact(monkeypatch, text, f"Jane{escape}Doe", "PERSON")

    assert result.text == f'String s = "<PERSON>{escape}<PERSON>";'


def test_span_starting_inside_an_escape_keeps_it_whole(monkeypatch):
    text = '{"note": "caf\\u00e9 jane@x.io"}'
    _stub(monkeypatch, ("EMAIL_ADDRESS", text.index("00e9"), text.index('"}')))

    result = redact_for_policy(text, _code())

    # The escape is kept whole; the run after it (a space is not structural) is masked.
    assert result.text == '{"note": "caf\\u00e9<EMAIL_ADDRESS>"}'
    json.loads(result.text)


def test_obrien_masks_as_two_placeholders(monkeypatch):
    """PRD Risk 4, with PERSON enabled."""
    policy = _code(entities=tuple(_CODE_ENTITIES) + ("PERSON",))

    result = _stub_redact(monkeypatch, "Patrick O'Brien", "Patrick O'Brien", "PERSON", policy)

    assert result == RedactionResult("<PERSON>'<PERSON>", ["PERSON"])


def test_run_without_alphanumerics_is_left_alone(monkeypatch):
    text = 'emails = ["jane@example.com", "x"]'

    result = _stub_redact(monkeypatch, text, 'jane@example.com", "')

    assert result.text == 'emails = ["<EMAIL_ADDRESS>", "x"]'


def test_span_of_only_structure_masks_nothing(monkeypatch):
    result = _stub_redact(monkeypatch, 'a = "", b', '"", ')

    assert result == RedactionResult('a = "", b', [])


@pytest.mark.parametrize("path", corpus_files._CODE_FILES, ids=corpus_files._ids(corpus_files._CODE_FILES))
def test_structural_characters_are_preserved_across_the_code_corpus(path):
    text = corpus_files._read(path)

    result = redact_for_policy(text, _code()).text

    for character in ('"', "'", "`", _BACKSLASH, "\n", "\r"):
        assert result.count(character) == text.count(character), repr(character)
    if path.suffix == ".json":
        json.loads(result)


# --- Overlap rule (longest, then earliest start, then entity name) -----------


def test_overlapping_spans_longest_wins(monkeypatch):
    text = "id 4155550134 5"
    _stub(monkeypatch, ("US_SSN", 3, 13), ("PHONE_NUMBER", 3, 15))

    assert redact_for_policy(text, _code()) == RedactionResult("id <PHONE_NUMBER>", ["PHONE_NUMBER"])


def test_overlapping_spans_equal_length_earliest_start_wins(monkeypatch):
    text = "abcdefgh"
    _stub(monkeypatch, ("US_SSN", 2, 6), ("PHONE_NUMBER", 0, 4))

    assert redact_for_policy(text, _code()) == RedactionResult("<PHONE_NUMBER>efgh", ["PHONE_NUMBER"])


def test_identical_spans_resolve_by_entity_name(monkeypatch):
    text = "call 219-09-9999"
    _stub(monkeypatch, ("US_SSN", 5, 16), ("PHONE_NUMBER", 5, 16))

    assert redact_for_policy(text, _code()) == RedactionResult("call <PHONE_NUMBER>", ["PHONE_NUMBER"])


def test_disjoint_spans_are_all_kept(monkeypatch):
    text = "a@x.io and b@y.io"
    _stub(monkeypatch, _span(text, "a@x.io", "EMAIL_ADDRESS"), _span(text, "b@y.io", "EMAIL_ADDRESS"))

    assert redact_for_policy(text, _code()).text == "<EMAIL_ADDRESS> and <EMAIL_ADDRESS>"


# --- AC 3: JSON-aware mode ---------------------------------------------------


def test_pii_in_a_string_value_is_replaced_inside_the_quotes(monkeypatch):
    text = '{"contact": "bob@x.io"}'

    assert _stub_redact(monkeypatch, text, '"bob@x.io"}').text == '{"contact": "<EMAIL_ADDRESS>"}'


def test_pii_in_a_key_is_replaced_inside_the_quotes(monkeypatch):
    text = '{"bob@x.io": {"name": "Bob"}}'

    assert _stub_redact(monkeypatch, text, '{"bob@x.io": ').text == '{"<EMAIL_ADDRESS>": {"name": "Bob"}}'


def test_number_token_becomes_a_quoted_placeholder(monkeypatch):
    text = '{"phone": 4155550134}'

    result = _stub_redact(monkeypatch, text, "4155550134", "PHONE_NUMBER")

    assert result == RedactionResult('{"phone": "<PHONE_NUMBER>"}', ["PHONE_NUMBER"])
    assert json.loads(result.text) == {"phone": "<PHONE_NUMBER>"}


@pytest.mark.parametrize("needle", ["55501", "-4155550134", ": -4155550134"])
def test_partial_span_over_a_number_replaces_the_whole_token(monkeypatch, needle):
    text = '{"phone": -4155550134, "n": 1}'

    result = _stub_redact(monkeypatch, text, needle, "PHONE_NUMBER")

    assert result.text == '{"phone": "<PHONE_NUMBER>", "n": 1}'


def test_two_spans_on_one_number_token_replace_it_once(monkeypatch):
    text = "[4155550134]"
    _stub(monkeypatch, ("PHONE_NUMBER", 1, 6), ("US_SSN", 6, 11))

    result = redact_for_policy(text, _code())

    assert result == RedactionResult('["<PHONE_NUMBER>"]', ["PHONE_NUMBER"])


@pytest.mark.parametrize("needle", [": ", "true", "null", "NaN", "\n  ", "}, "])
def test_spans_over_punctuation_literals_or_whitespace_are_dropped(monkeypatch, needle):
    text = '{"a": true,\n  "b": null, "c": NaN, "d": {}, "e": 1}'

    result = _stub_redact(monkeypatch, text, needle)

    assert result == RedactionResult(text, [])


def test_span_across_several_tokens_is_clipped_to_each(monkeypatch):
    text = '{"jane@x.io": "jane@x.io", "n": 4155550134}'
    _stub(monkeypatch, ("EMAIL_ADDRESS", 1, len(text) - 1))

    result = redact_for_policy(text, _code())

    assert result.text == '{"<EMAIL_ADDRESS>": "<EMAIL_ADDRESS>", "<EMAIL_ADDRESS>": "<EMAIL_ADDRESS>"}'
    json.loads(result.text)


def test_json_formatting_survives():
    text = '{\n    "contact": "bob@x.io",\n\t"id": 7\n}\n'

    result = redact_for_policy(text, _code())

    assert result.text == '{\n    "contact": "<EMAIL_ADDRESS>",\n\t"id": 7\n}\n'


def test_prd_user_story_4():
    text = '{"id": 7, "contact": "bob@x.io", "phone": 4155550134}'

    result = redact_for_policy(text, _code())

    assert result == RedactionResult(
        '{"id": 7, "contact": "<EMAIL_ADDRESS>", "phone": "<PHONE_NUMBER>"}', ["EMAIL_ADDRESS", "PHONE_NUMBER"]
    )


@pytest.mark.parametrize("path", corpus_files._ALL_JSON, ids=corpus_files._ids(corpus_files._ALL_JSON))
def test_every_json_corpus_file_still_parses(path):
    result = redact_for_policy(corpus_files._read(path), _code())

    json.loads(result.text)
    assert result.entities


def test_number_token_cards_become_strings():
    text = corpus_files._read(corpus_files._PII / "json" / "payment-webhook.json")

    result = redact_for_policy(text, _code()).text

    assert "4111111111111111" in text and "4111111111111111" not in result
    assert '"number": "<CREDIT_CARD>"' in result


def test_number_token_phones_become_strings():
    text = corpus_files._read(corpus_files._PII / "json" / "crm-contact-search.json")

    result = redact_for_policy(text, _code()).text

    phones = [node for kind, key, node, _ in corpus_files._walk(json.loads(result)) if kind == "value" and key is None]
    assert '"phone": "<PHONE_NUMBER>"' in result
    assert not any(isinstance(v, int) and v > 10**9 for v in phones)


def test_directory_keys_are_masked():
    text = corpus_files._read(corpus_files._PII / "json" / "directory-index-by-email.json")

    result = redact_for_policy(text, _code()).text

    assert '"jane.doe@example.com": {' in text
    assert '"<EMAIL_ADDRESS>": {' in result and '"jane.doe@example.com"' not in result


@pytest.mark.parametrize("text", ['{name: "x", mail: "bob@x.io"}', '"bob@x.io"', "[bob@x.io"])
def test_non_json_text_uses_structure_safe_mode_only(monkeypatch, text):
    """Not a JSON object or array: no clipping, no post-condition, no raise."""
    result = _stub_redact(monkeypatch, text, "bob@x.io")

    assert result.text == text.replace("bob@x.io", "<EMAIL_ADDRESS>")


def test_top_level_number_is_not_json_mode(monkeypatch):
    """A top-level scalar is not an object or array; outside JSON mode the
    number is masked in place, unquoted."""
    assert _stub_redact(monkeypatch, "4155550134", "4155550134", "PHONE_NUMBER").text == "<PHONE_NUMBER>"


def test_leading_whitespace_json_is_detected(monkeypatch):
    text = '\n  [4155550134]'

    assert _stub_redact(monkeypatch, text, "4155550134", "PHONE_NUMBER").text == '\n  ["<PHONE_NUMBER>"]'


# --- AC 4: JSON post-condition fails closed ----------------------------------


def test_post_condition_raises_on_invalid_json(monkeypatch):
    """With the scanner and clipping correct, no analyzer span can make a valid
    document invalid (plan P14): the post-condition is a backstop. To reach it,
    the stub analyzer is paired with a scanner that misreports the whole
    document as one string token, so the span over `a": 1` is replaced as
    string interior and the result is `{"<EMAIL_ADDRESS>"<EMAIL_ADDRESS>}`."""
    text = '{"a": 1}'
    _stub(monkeypatch, ("EMAIL_ADDRESS", 2, len(text) - 1))
    monkeypatch.setattr(pii_redactor, "_json_tokens", lambda t: [("string", 0, len(t))])

    with pytest.raises(PiiRedactorError, match=r"^redaction would produce invalid JSON$") as excinfo:
        redact_for_policy(text, _code())

    assert text not in str(excinfo.value)


def test_analysis_failure_is_a_pii_redactor_error(monkeypatch):
    class _Failing:
        def analyze(self, **kwargs):
            raise OSError("boom")

    monkeypatch.setattr(pii_redactor, "_get_analyzer", lambda entities=None: _Failing())

    with pytest.raises(PiiRedactorError, match="^PII analysis failed: boom$"):
        redact_for_policy("jane@example.com", _code())


# --- AC 5: chat is redact() ---------------------------------------------------


@pytest.mark.parametrize("text", [case[0] for case in REDACT_CASES])
def test_chat_policy_equals_redact(text):
    result = redact_for_policy(text, get_pii_policy("chat"))

    assert result == redact(text)
    assert isinstance(result, tuple)


def test_chat_policy_delegates_to_redact(monkeypatch):
    redact_calls, analyzer_calls = [], []
    real_redact, real_get = pii_redactor.redact, pii_redactor._get_analyzer

    def _spy_redact(text):
        redact_calls.append(text)
        return real_redact(text)

    def _spy_get(entities=None):
        analyzer_calls.append(entities)
        return real_get(entities)

    monkeypatch.setattr(pii_redactor, "redact", _spy_redact)
    monkeypatch.setattr(pii_redactor, "_get_analyzer", _spy_get)

    redact_for_policy("Mail jane.doe@example.com", get_pii_policy("chat"))

    assert redact_calls == ["Mail jane.doe@example.com"]
    assert analyzer_calls == [None]


def test_chat_policy_fields_match_what_redact_reads():
    """P3: delegating is only faithful while chat is built from redact()'s settings."""
    chat = get_pii_policy("chat")

    assert chat.structure_safe is False
    assert chat.entities == tuple(settings.pii_entities_list)
    assert chat.threshold == settings.PII_SCORE_THRESHOLD


# --- Analyzer selection, master switch, entities, windows --------------------


def test_default_code_policy_never_touches_the_full_analyzer(monkeypatch):
    tripwire_log = []
    monkeypatch.setattr(pii_redactor, "_analyzer", _Tripwire(tripwire_log))

    result = redact_for_policy("Mail jane@example.com today.", _code())

    assert result.text == "Mail <EMAIL_ADDRESS> today."
    assert tripwire_log == []


def test_analyzer_is_selected_by_policy_entities(monkeypatch):
    seen = []
    stub = _StubAnalyzer([])

    def _spy_get(entities=None):
        seen.append(entities)
        return stub

    monkeypatch.setattr(pii_redactor, "_get_analyzer", _spy_get)
    policy = _code(entities=("EMAIL_ADDRESS", "PERSON"))

    redact_for_policy("anything", policy)

    assert seen == [("EMAIL_ADDRESS", "PERSON")]


def test_master_switch_off_returns_text_unchanged(monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
    monkeypatch.setattr(pii_redactor, "_get_analyzer", lambda entities=None: pytest.fail("analyzer reached"))

    assert redact_for_policy("jane@example.com", _code()) == RedactionResult("jane@example.com", [])


def test_empty_text_returns_empty():
    assert redact_for_policy("", _code()) == RedactionResult("", [])


def test_entities_are_sorted_and_only_those_replaced(monkeypatch):
    text = 'x = "4155550134", "", "a@b.io"'
    _stub(
        monkeypatch,
        _span(text, "a@b.io", "EMAIL_ADDRESS"),
        _span(text, "4155550134", "PHONE_NUMBER"),
        _span(text, '""', "US_SSN"),
    )

    result = redact_for_policy(text, _code())

    assert result == RedactionResult('x = "<PHONE_NUMBER>", "", "<EMAIL_ADDRESS>"', ["EMAIL_ADDRESS", "PHONE_NUMBER"])


@pytest.mark.parametrize("path", corpus_files._CODE_FILES, ids=corpus_files._ids(corpus_files._CODE_FILES))
def test_analysis_windows_match_the_benchmark_reference(path):
    text = corpus_files._read(path)
    text = text * (40_001 // len(text) + 1)

    assert pii_redactor._analysis_windows(text) == bench._chunks(text, 20_000)


def test_a_line_longer_than_the_window_is_cut_hard():
    windows = pii_redactor._analysis_windows("y" * 45_000)

    assert [(offset, len(window)) for offset, window in windows] == [(0, 20_000), (20_000, 20_000), (40_000, 5_000)]


def test_pii_beyond_the_first_window_is_masked_at_the_right_offset():
    prose = "".join(f"Line {i} of the build log says nothing personal.\n" for i in range(700))
    assert len(prose) > 30_000
    text = prose + "Escalate to maria.lopez@corp.com now.\n" + prose

    result = redact_for_policy(text, _code())

    assert result == RedactionResult(prose + "Escalate to <EMAIL_ADDRESS> now.\n" + prose, ["EMAIL_ADDRESS"])


def test_blank_windows_skip_the_analyzer(monkeypatch):
    calls = []

    class _Counting(_StubAnalyzer):
        def analyze(self, **kwargs):
            calls.append(kwargs["text"])
            return []

    monkeypatch.setattr(pii_redactor, "_get_analyzer", lambda entities=None: _Counting([]))
    fence = "```\n" + ("x = 1\n" * 8_000) + "```\n"

    redact_for_policy("Intro line.\n" + fence + "Outro line.\n", _code())

    assert all(not window.isspace() for window in calls)
    assert len(calls) == 2
