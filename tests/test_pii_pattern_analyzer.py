"""PRD-012 STORY-006: the pattern-only analyzer, selected by the entity list.

AC 1, 2 and 4, and AC 3 at the function level, are here. AC 3's FastAPI
lifespan path is in tests/test_main.py (the PRD-012 STORY-006 block). AC 5 is
proved by tests/test_pii_redactor.py and tests/test_pii_characterization.py
passing, unedited.

The full analyzer runs on `en_core_web_sm` here, the tests/test_pii_redactor.py
precedent: these tests check *which object* is selected, not lg's scores, which
tests/test_pii_characterization.py already pins. The tokenizer-only analyzer
loads no model at all.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
import spacy
from presidio_analyzer.predefined_recognizers import SpacyRecognizer

from app.config import _PRESIDIO_ENTITY_NAMES, settings
import app.services.pii_redactor as pii_redactor

_CODE_ENTITIES = ["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN", "IBAN_CODE"]
_PATTERN_ONLY_TYPES = sorted(_PRESIDIO_ENTITY_NAMES - pii_redactor._NER_ENTITY_TYPES)


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


def _counting(monkeypatch, name):
    """Wrap pii_redactor.<name> so each call is recorded; returns the call list."""
    calls = []
    original = getattr(pii_redactor, name)

    def _wrapper():
        calls.append(1)
        return original()

    monkeypatch.setattr(pii_redactor, name, _wrapper)
    return calls


def _raising(*args, **kwargs):
    raise OSError("boom")


def _phone_score(analyzer, text):
    results = analyzer.analyze(text=text, language="en", entities=["PHONE_NUMBER"], score_threshold=0)
    assert len(results) == 1
    return round(results[0].score, 2)


# --- The NER set (story Technical Notes) ------------------------------------------


def test_ner_entity_types_are_exactly_what_spacy_recognizer_serves():
    """A drift guard: the constant is written out, never inferred at runtime, so
    a Presidio bump that adds or moves a NER-served type has to turn this red."""
    assert pii_redactor._NER_ENTITY_TYPES == frozenset(SpacyRecognizer().supported_entities)


def test_ner_entity_types_are_known_presidio_names():
    assert pii_redactor._NER_ENTITY_TYPES <= _PRESIDIO_ENTITY_NAMES


# --- AC 1: no NER type -> tokenizer-only, built once, cached ----------------------


def test_code_entities_select_the_tokenizer_only_analyzer():
    analyzer = pii_redactor._get_analyzer(_CODE_ENTITIES)

    assert type(analyzer.nlp_engine) is pii_redactor._TokenizerOnlySpacyNlpEngine
    assert analyzer.nlp_engine.nlp["en"].pipe_names == ["pii_lower_as_lemma"]  # no ner
    assert analyzer is pii_redactor._pattern_analyzer
    assert pii_redactor._analyzer is None, "the full analyzer must not be built for a pattern-only list"


@pytest.mark.parametrize("entity", _PATTERN_ONLY_TYPES)
def test_every_pattern_only_type_alone_selects_the_tokenizer_only_analyzer(entity):
    analyzer = pii_redactor._get_analyzer([entity])

    assert type(analyzer.nlp_engine) is pii_redactor._TokenizerOnlySpacyNlpEngine
    assert pii_redactor._analyzer is None


def test_pattern_analyzer_constructed_only_once(monkeypatch):
    """The equivalent of test_pii_redactor.py's test_analyzer_engine_constructed_only_once
    for the second analyzer (STORY-006 Technical Notes). The order of the list
    does not matter."""
    build_calls = _counting(monkeypatch, "_build_pattern_analyzer")

    first = pii_redactor._get_analyzer(_CODE_ENTITIES)
    second = pii_redactor._get_analyzer(_CODE_ENTITIES)
    reordered = pii_redactor._get_analyzer(reversed(_CODE_ENTITIES))

    assert first is second is reordered
    assert len(build_calls) == 1


def test_tokenizer_only_analyzer_keeps_context_boosts():
    """Carried over from tests/test_measure_pii_latency.py, on the production
    analyzer: without lemmas "phone" would not boost and this would be 0.40."""
    analyzer = pii_redactor._get_analyzer(_CODE_ENTITIES)

    assert _phone_score(analyzer, "My phone is 415-555-0134 please.") == 0.75
    assert _phone_score(analyzer, "Call 415-555-0134") == 0.40  # `call` is not a context word


# --- AC 2: a NER type -> today's full singleton, the one redact() uses -------------


@pytest.mark.parametrize(
    "entities",
    [
        ["PERSON"],
        ["PERSON", *_CODE_ENTITIES],
        ["LOCATION"],
        ["ORGANIZATION"],
        ["NRP"],
        ["DATE_TIME"],
        ["EMAIL_ADDRESS", "DATE_TIME"],
    ],
)
def test_a_ner_type_selects_the_full_analyzer(entities):
    pii_redactor.redact("jane@example.com")

    assert pii_redactor._get_analyzer(entities) is pii_redactor._analyzer
    assert pii_redactor._pattern_analyzer is None, "nothing extra is built for a NER list"


def test_no_argument_is_the_full_analyzer():
    """The pre-PRD-012 contract the characterization fixture and the benchmark
    script call (plan F-1)."""
    analyzer = pii_redactor._get_analyzer()

    assert analyzer is pii_redactor._get_analyzer(["PERSON"])
    assert not isinstance(analyzer.nlp_engine, pii_redactor._TokenizerOnlySpacyNlpEngine)


def test_redact_uses_the_full_analyzer_even_with_a_pattern_only_pii_entities(monkeypatch):
    """`chat` must not move by a byte (PRD-012 Section 11): an operator whose
    PII_ENTITIES holds no NER type still gets the full analyzer under redact()."""
    monkeypatch.setattr(settings, "PII_ENTITIES", "EMAIL_ADDRESS")
    pattern_builds = _counting(monkeypatch, "_build_pattern_analyzer")

    assert pii_redactor.redact("a@b.com") == ("<EMAIL_ADDRESS>", ["EMAIL_ADDRESS"])
    assert pattern_builds == []
    assert pii_redactor._pattern_analyzer is None


# --- AC 3: load() prebuilds both, and a failure stops it -------------------------


def test_load_builds_the_full_and_the_code_analyzer(monkeypatch):
    full_builds = _counting(monkeypatch, "_build_analyzer")
    pattern_builds = _counting(monkeypatch, "_build_pattern_analyzer")

    pii_redactor.load()

    assert (len(full_builds), len(pattern_builds)) == (1, 1)
    assert pii_redactor._analyzer is not None
    assert pii_redactor._pattern_analyzer is not None

    pii_redactor._get_analyzer(settings.pii_entities_code_list)
    pii_redactor.redact("a request, no pii")

    assert (len(full_builds), len(pattern_builds)) == (1, 1), "nothing is built on a request"


def test_load_with_a_ner_type_in_code_entities_builds_only_the_full_analyzer(monkeypatch):
    monkeypatch.setattr(settings, "PII_ENTITIES_CODE", "PERSON,EMAIL_ADDRESS")
    full_builds = _counting(monkeypatch, "_build_analyzer")
    pattern_builds = _counting(monkeypatch, "_build_pattern_analyzer")

    pii_redactor.load()

    assert (len(full_builds), len(pattern_builds)) == (1, 0)
    assert pii_redactor._pattern_analyzer is None


def test_load_is_a_noop_for_both_when_redaction_disabled(monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)

    pii_redactor.load()

    assert pii_redactor._analyzer is None
    assert pii_redactor._pattern_analyzer is None


def test_a_tokenizer_only_build_failure_is_a_startup_error_not_a_fallback(monkeypatch):
    """STORY-006: a failure to build the pattern-only analyzer "never silently
    falls back to the full analyzer, which would reintroduce NER false
    positives and cost without anyone noticing"."""
    monkeypatch.setattr(pii_redactor.spacy, "blank", _raising)

    with pytest.raises(pii_redactor.PiiRedactorError) as excinfo:
        pii_redactor.load()

    assert "PII_ENTITIES_CODE" in str(excinfo.value)
    assert "boom" in str(excinfo.value)
    assert pii_redactor._pattern_analyzer is None
    assert pii_redactor._analyzer is not None, "load() built the full analyzer first"

    with pytest.raises(pii_redactor.PiiRedactorError):
        pii_redactor._get_analyzer(_CODE_ENTITIES)


# --- AC 4: email and phone found; en_core_web_lg never touched --------------------


class _Tripwire:
    """Stands in for the full analyzer: any attribute access is recorded and fails."""

    def __init__(self, log):
        object.__setattr__(self, "_log", log)

    def __getattr__(self, name):
        self._log.append(name)
        raise AssertionError(f"the full analyzer was reached: .{name}")


def test_pattern_analyzer_detects_email_and_phone_without_touching_en_core_web_lg(monkeypatch):
    """"A spy on en_core_web_lg records no call", made concrete (plan P10).
    Loading lg only to spy on it would cost seconds and prove less. Instead:
    the full-analyzer slot holds a tripwire, so reaching it is recorded;
    _build_analyzer is wrapped, so building it is recorded; spacy.load and
    spacy.cli.download are wrapped, so loading or fetching *any* model is
    recorded."""
    tripwire_log = []
    monkeypatch.setattr(pii_redactor, "_analyzer", _Tripwire(tripwire_log))
    full_builds = _counting(monkeypatch, "_build_analyzer")
    loads, downloads = [], []
    real_load = spacy.load

    def _recording_load(*args, **kwargs):
        loads.append(args)
        return real_load(*args, **kwargs)

    def _refusing_download(*args, **kwargs):
        downloads.append(args)
        raise RuntimeError("download refused")

    monkeypatch.setattr(spacy, "load", _recording_load)
    monkeypatch.setattr(spacy.cli, "download", _refusing_download)

    results = pii_redactor._get_analyzer(_CODE_ENTITIES).analyze(
        text="jane@example.com called 415-555-0134",
        language="en",
        entities=_CODE_ENTITIES,
        score_threshold=settings.PII_SCORE_THRESHOLD_CODE,
    )

    assert {(r.entity_type, r.start, r.end) for r in results} == {
        ("EMAIL_ADDRESS", 0, 16),
        ("PHONE_NUMBER", 24, 36),
    }
    assert tripwire_log == []
    assert full_builds == []
    assert loads == []
    assert downloads == []
