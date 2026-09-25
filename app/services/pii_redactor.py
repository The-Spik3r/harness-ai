from typing import Iterable, List, Optional, Tuple

import spacy
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider, SpacyNlpEngine
from presidio_anonymizer import AnonymizerEngine
from spacy.language import Language

from app.config import settings

_analyzer: Optional[AnalyzerEngine] = None
_pattern_analyzer: Optional[AnalyzerEngine] = None
_anonymizer: Optional[AnonymizerEngine] = None


class PiiRedactorError(Exception):
    pass


# The entity types Presidio 2.2.364's SpacyRecognizer serves (PRD-012 D7). A
# list containing any of them needs the NER model, so it gets the full
# analyzer; a list with none of them gets the tokenizer-only one. Written out,
# never read from Presidio at runtime (STORY-006), and pinned to the live
# recognizer by tests/test_pii_pattern_analyzer.py.
_NER_ENTITY_TYPES = frozenset(
    {
        "PERSON",  # in today's PII_ENTITIES; NER-only, and the main false-positive source on code (STORY-003: 11 on code/)
        "LOCATION",  # in today's PII_ENTITIES; NER-only (STORY-003: 7 false positives on code/)
        "ORGANIZATION",  # served only by SpacyRecognizer
        "NRP",  # served only by SpacyRecognizer
        "DATE_TIME",  # SpacyRecognizer *and* the pattern DateRecognizer; on a blank pipeline only the pattern half runs, so the analyzers would disagree
    }
)


@Language.component("pii_lower_as_lemma")
def pii_lower_as_lemma(doc):
    """Give the blank pipeline lemmas, so Presidio's context words still boost.

    Presidio's context enhancer compares context words ("phone", "mobile",
    "social security") against `token.lemma_`. spacy.blank("en") has no
    lemmatizer, so every lemma is empty and no score is ever boosted: "My phone
    is 415-555-0134" drops from 0.75 to 0.40. STORY-003 measured this route at
    4 differences from en_core_web_lg, every one of them masking more.

    Named apart from scripts/measure_pii_latency.py's `lower_as_lemma`: spaCy
    component names are process-global, and a second registration under the
    same name silently replaces the first.
    """
    for token in doc:
        token.lemma_ = token.lower_
    return doc


class _TokenizerOnlySpacyNlpEngine(SpacyNlpEngine):
    """A SpacyNlpEngine over spacy.blank("en"): a tokenizer and lemmas, no tagger, parser or NER.

    A subclass, not NlpEngineProvider: Presidio downloads any model name that
    is neither an installed package nor a path, and for a blank model that
    download ends in SystemExit (STORY-003, route 1).
    """

    def __init__(self):
        super().__init__(models=[{"lang_code": "en", "model_name": "blank"}])

    def load(self) -> None:
        nlp = spacy.blank("en")
        nlp.add_pipe("pii_lower_as_lemma")
        self.nlp = {"en": nlp}


def _build_analyzer() -> AnalyzerEngine:
    nlp_configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": settings.PII_NLP_MODEL}],
    }
    try:
        nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
        return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    except Exception as exc:
        raise PiiRedactorError(f"Failed to load Presidio NLP model {settings.PII_NLP_MODEL!r}: {exc}") from exc


def _build_pattern_analyzer() -> AnalyzerEngine:
    try:
        nlp_engine = _TokenizerOnlySpacyNlpEngine()
        nlp_engine.load()
        return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    except Exception as exc:
        raise PiiRedactorError(
            "Failed to build the tokenizer-only Presidio analyzer that PII_ENTITIES_CODE "
            f"selects (spacy.blank('en')): {exc}"
        ) from exc


def _get_analyzer(entities: Optional[Iterable[str]] = None) -> AnalyzerEngine:
    """The analyzer for an entity list (PRD-012 F6).

    - None: today's full analyzer over PII_NLP_MODEL. This is the pre-PRD-012
      no-argument contract, which redact(), the characterization fixture and the
      benchmark script rely on.
    - A list with any NER type (_NER_ENTITY_TYPES): the same full analyzer.
    - Otherwise: the tokenizer-only analyzer. It never falls back to the full
      one; a build failure raises PiiRedactorError.
    """
    global _analyzer, _pattern_analyzer
    if entities is None or not _NER_ENTITY_TYPES.isdisjoint(entities):
        if _analyzer is None:
            _analyzer = _build_analyzer()
        return _analyzer
    if _pattern_analyzer is None:
        _pattern_analyzer = _build_pattern_analyzer()
    return _pattern_analyzer


def _get_anonymizer() -> AnonymizerEngine:
    global _anonymizer
    if _anonymizer is None:
        _anonymizer = AnonymizerEngine()
    return _anonymizer


def load() -> None:
    """Build every analyzer the configured profiles need; startup only, in both lifespans.

    Today's full analyzer, then the one PII_ENTITIES_CODE selects (the same
    object when that list has a NER type), so neither is built on a request
    (PRD-012 F6). A failure raises PiiRedactorError and stops the boot.
    PII_REDACTION_ENABLED=false builds neither.
    """
    if not settings.PII_REDACTION_ENABLED:
        return
    _get_analyzer()
    _get_analyzer(settings.pii_entities_code_list)


def redact(text: str) -> Tuple[str, List[str]]:
    if not settings.PII_REDACTION_ENABLED or not text:
        return text, []

    # No argument on purpose: `chat` always runs the full analyzer, whatever PII_ENTITIES holds.
    analyzer = _get_analyzer()
    try:
        results = analyzer.analyze(
            text=text,
            language="en",
            entities=settings.pii_entities_list,
            score_threshold=settings.PII_SCORE_THRESHOLD,
        )
    except Exception as exc:
        raise PiiRedactorError(f"PII analysis failed: {exc}") from exc

    if not results:
        return text, []

    anonymizer = _get_anonymizer()
    try:
        anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
    except Exception as exc:
        raise PiiRedactorError(f"PII anonymization failed: {exc}") from exc

    entities_found = sorted({result.entity_type for result in results})
    return anonymized.text, entities_found
