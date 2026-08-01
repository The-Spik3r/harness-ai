from typing import List, Optional, Tuple

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

from app.config import settings

_analyzer: Optional[AnalyzerEngine] = None
_anonymizer: Optional[AnonymizerEngine] = None


class PiiRedactorError(Exception):
    pass


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


def _get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        _analyzer = _build_analyzer()
    return _analyzer


def _get_anonymizer() -> AnonymizerEngine:
    global _anonymizer
    if _anonymizer is None:
        _anonymizer = AnonymizerEngine()
    return _anonymizer


def load() -> None:
    if not settings.PII_REDACTION_ENABLED:
        return
    _get_analyzer()


def redact(text: str) -> Tuple[str, List[str]]:
    if not settings.PII_REDACTION_ENABLED or not text:
        return text, []

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
