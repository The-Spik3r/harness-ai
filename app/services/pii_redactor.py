import bisect
import json
import re
from typing import Iterable, List, NamedTuple, Optional, Tuple

import spacy
from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider, SpacyNlpEngine
from presidio_anonymizer import AnonymizerEngine
from spacy.language import Language

from app.config import settings
from app.services.pattern_detector import strip_fenced_blocks
from app.services.pii_policy import PiiPolicy

_analyzer: Optional[AnalyzerEngine] = None
_pattern_analyzer: Optional[AnalyzerEngine] = None
_anonymizer: Optional[AnonymizerEngine] = None


class PiiRedactorError(Exception):
    pass


class RedactionResult(NamedTuple):
    """What redact_for_policy() returns (PRD-012 F7): the masked text and the
    sorted entity types it masked.

    A NamedTuple so it compares equal to, and unpacks like, the `(text,
    entities)` tuple redact() returns: under `chat` the two are the same value
    (STORY-008 AC 5), and a caller can swap one call for the other.
    """

    text: str
    entities: List[str]


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


# --------------------------------------------------------------------------
# redact_for_policy() helpers (PRD-012 STORY-008). Pure apart from _analyze().
# --------------------------------------------------------------------------

#: Analysis window (STORY-003 R3). Analyzer cost is superlinear in the length
#: of one string: one 200,000-character message took p95 2,712 ms unchunked
#: and 751 ms in line-aligned 20,000-character windows, with identical spans.
#: PII_MAX_CHARACTERS_CODE = 200,000 is only within budget on this condition.
_ANALYSIS_WINDOW_CHARACTERS = 20_000

#: Never replaced (PRD-012 Section 6.6, rule 1): quotes, backticks and line
#: breaks. The backslash is covered by _ESCAPE, which keeps the whole escape
#: sequence. The placeholder alphabet (`<`, `>`, `A-Z`, `_`) contains none of
#: these, so a placeholder can never introduce one either.
_STRUCTURAL_CHARACTERS = frozenset("\"'`\r\n")

#: An escape sequence, kept whole. Keeping only the backslash is not enough:
#: `"...\nAisha Bello"` (tests/corpora/pii/json/ticket-thread-export.json)
#: would become `"...\<PERSON>"`, an invalid escape in JSON and Java. One
#: left-to-right scan, so `\\` pairs are consumed correctly; `.` also covers a
#: backslash that no known escape follows (`C:\Users` keeps `\U`).
_ESCAPE = re.compile(r"\\(?:u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|x[0-9A-Fa-f]{2}|.)", re.DOTALL)

#: JSON string, number or bare word (true/false/null/NaN/Infinity), located by
#: offset (PRD-012 Section 8). Only run on text json.loads() accepted, so it
#: need not validate; punctuation and whitespace fall between matches.
_JSON_TOKEN = re.compile(
    r'"(?:[^"\\]+|\\.)*"|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|[A-Za-z]+',
    re.DOTALL,
)


def _analysis_windows(text: str, size: int = _ANALYSIS_WINDOW_CHARACTERS) -> list[tuple[int, str]]:
    """(offset, window) pairs of at most `size` characters, each ending just
    after a newline where one exists, so no line is split; the windows rejoin
    to `text`. A copy of scripts/measure_pii_latency.py's `_chunks` (app/ does
    not import scripts/), pinned to it by tests/test_pii_structure_safe.py.
    A line longer than `size` is cut hard."""
    windows = []
    position = 0
    while position < len(text):
        end = min(position + size, len(text))
        if end < len(text):
            newline = text.rfind("\n", position, end)
            if newline != -1:
                end = newline + 1
        windows.append((position, text[position:end]))
        position = end
    return windows


def _analyze(analysis: str, policy: PiiPolicy) -> list[RecognizerResult]:
    """Analyzer spans over `analysis`, window by window, with offsets shifted
    back into `analysis` (STORY-003 R3). The analyzer is the one the policy's
    entity list selects (PRD-012 F6), never the no-argument `chat` one."""
    analyzer = _get_analyzer(policy.entities)
    results = []
    try:
        for offset, window in _analysis_windows(analysis):
            if window.isspace():  # a blanked fence: nothing to find, skip the analyzer call
                continue
            for result in analyzer.analyze(
                text=window,
                language="en",
                entities=list(policy.entities),
                score_threshold=policy.threshold,
            ):
                results.append(
                    RecognizerResult(result.entity_type, result.start + offset, result.end + offset, result.score)
                )
    except Exception as exc:
        raise PiiRedactorError(f"PII analysis failed: {exc}") from exc
    return results


def _take(taken: list[tuple[int, int, str, str]], start: int, end: int, replacement: str, entity_type: str) -> None:
    """Insert a range into `taken` (sorted, non-overlapping) unless it
    overlaps one already there; the earlier-taken range wins."""
    index = bisect.bisect_left(taken, (end,))
    if index and taken[index - 1][1] > start:
        return
    taken.insert(index, (start, end, replacement, entity_type))


def _resolve_overlaps(results: Iterable[RecognizerResult]) -> list[RecognizerResult]:
    """Non-overlapping spans, in priority order: longest first, then earliest
    start, then entity type name; a span overlapping an accepted one is
    dropped (PRD-012 STORY-008)."""
    taken: list[tuple[int, int, str, str]] = []
    accepted = []
    for result in sorted(results, key=lambda r: (-(r.end - r.start), r.start, r.entity_type)):
        if result.end <= result.start:
            continue
        before = len(taken)
        _take(taken, result.start, result.end, "", result.entity_type)
        if len(taken) > before:
            accepted.append(result)
    return accepted


def _escape_intervals(text: str) -> list[tuple[int, int]]:
    """Every escape sequence in `text` as sorted (start, end) intervals."""
    if "\\" not in text:
        return []
    return [(match.start(), match.end()) for match in _ESCAPE.finditer(text)]


def _structure_safe_runs(
    text: str, analysis: str, escapes: list[tuple[int, int]], start: int, end: int
) -> list[tuple[int, int]]:
    """The maximal runs of [start, end) with no structural position and at
    least one alphanumeric character (PRD-012 Section 6.6, rule 1).

    A position is structural when its character is a quote, a backtick or a
    line break, when it lies inside an escape sequence, or when it lies inside
    a blanked fence (`analysis[i] != text[i]`): the analyzer cannot match
    inside a run of newlines, and this guarantees fenced bytes never change
    whatever it returns.
    """
    structural = [
        text[i] in _STRUCTURAL_CHARACTERS or analysis[i] != text[i] for i in range(start, end)
    ]
    index = max(bisect.bisect_right(escapes, (start, len(text) + 1)) - 1, 0)
    while index < len(escapes) and escapes[index][0] < end:
        escape_start, escape_end = escapes[index]
        for i in range(max(escape_start, start), min(escape_end, end)):
            structural[i - start] = True
        index += 1

    runs = []
    run_start = None
    for i in range(start, end + 1):
        if i < end and not structural[i - start]:
            if run_start is None:
                run_start = i
            continue
        if run_start is not None:
            if any(character.isalnum() for character in text[run_start:i]):
                runs.append((run_start, i))
            run_start = None
    return runs


def _is_json_document(text: str) -> bool:
    """JSON-aware mode's test (PRD-012 Section 6.6, rule 2): the stripped text
    starts with `{` or `[` and json.loads() accepts it."""
    if text.lstrip()[:1] not in ("{", "["):
        return False
    try:
        json.loads(text)
    except (ValueError, RecursionError):
        return False
    return True


def _json_tokens(text: str) -> list[tuple[str, int, int]]:
    """("string" | "number", start, end) for every string and number token of
    a document json.loads() accepted, in order; a string's range includes its
    quotes. true/false/null/NaN/Infinity, punctuation and whitespace are not
    tokens here, so a span over them alone is dropped."""
    tokens = []
    for match in _JSON_TOKEN.finditer(text):
        first = match.group()[0]
        if first == '"':
            tokens.append(("string", match.start(), match.end()))
        elif first == "-" or first.isdigit():
            tokens.append(("number", match.start(), match.end()))
    return tokens


def _replacement_ranges(
    text: str,
    analysis: str,
    accepted: list[RecognizerResult],
    json_tokens: Optional[list[tuple[str, int, int]]],
) -> list[tuple[int, int, str, str]]:
    """(start, end, replacement, entity_type) ranges, sorted and disjoint.

    Outside JSON mode, each span becomes its structure-safe runs. In JSON
    mode, each span is intersected with the tokens it overlaps: inside a
    string, the runs of the string's interior; over any part of a number, the
    whole token as a quoted placeholder; anything else is dropped. Spans are
    taken in priority order, so where two spans widen onto the same number
    token the first one wins.
    """
    escapes = _escape_intervals(text)
    token_starts = [token[1] for token in json_tokens] if json_tokens is not None else []
    taken: list[tuple[int, int, str, str]] = []
    for result in accepted:
        placeholder = f"<{result.entity_type}>"
        if json_tokens is None:
            pieces = [(result.start, result.end)]
        else:
            pieces = []
            index = max(bisect.bisect_right(token_starts, result.start) - 1, 0)
            while index < len(json_tokens) and json_tokens[index][1] < result.end:
                kind, token_start, token_end = json_tokens[index]
                index += 1
                if token_end <= result.start:
                    continue
                if kind == "number":
                    _take(taken, token_start, token_end, f'"{placeholder}"', result.entity_type)
                    continue
                start, end = max(result.start, token_start + 1), min(result.end, token_end - 1)
                if start < end:
                    pieces.append((start, end))
        for start, end in pieces:
            for run_start, run_end in _structure_safe_runs(text, analysis, escapes, start, end):
                _take(taken, run_start, run_end, placeholder, result.entity_type)
    return taken


def _splice(text: str, ranges: list[tuple[int, int, str, str]]) -> str:
    """`text` with each sorted, disjoint range replaced, in one join."""
    out = []
    position = 0
    for start, end, replacement, _ in ranges:
        out.append(text[position:start])
        out.append(replacement)
        position = end
    out.append(text[position:])
    return "".join(out)


def redact_for_policy(text: str, policy: PiiPolicy) -> RedactionResult:
    """Mask `text` under `policy` (PRD-012 Sections 6.5, 6.6; F7).

    PII_REDACTION_ENABLED=false, or empty text, returns `text` unchanged. A
    policy without `structure_safe` (`chat`) is redact(), byte for byte:
    today's AnonymizerEngine path, reading the same PII_ENTITIES and
    PII_SCORE_THRESHOLD the `chat` policy is built from.

    A structure-safe policy (`code`) runs, in order:

    1. **Fence blanking.** With `skip_fenced_blocks`, the analyzer sees
       strip_fenced_blocks(text): every fenced character becomes a newline, so
       the length is unchanged and every offset it returns is an offset into
       `text`. Inline backtick spans are analyzed (D2). An unterminated fence
       runs to the end of the text.
    2. **Analysis** with the analyzer `policy.entities` selects, at
       `policy.threshold`, in line-aligned windows of at most 20,000
       characters (STORY-003 R3). A line longer than a window is cut hard, and
       a span across that cut can be missed.
    3. **Overlaps.** Longest span first, then earliest start, then entity type
       name; a span overlapping one already accepted is dropped.
    4. **Structure-safe splitting.** Quotes (`"`, `'`), backticks, line breaks
       and whole escape sequences (`\\n`, `\\"`, `\\\\`, `\\u00e9`, ...) are
       never replaced, and neither is any fenced character. Each span is split
       into the runs between them, and a run with no alphanumeric character is
       left alone: `O'Brien` masks as `<PERSON>'<PERSON>`. Escapes are kept
       whole, not only their backslash, because `\\<PERSON>` is itself an
       invalid escape.
    5. **JSON-aware mode**, when the stripped text starts with `{` or `[` and
       json.loads() accepts it. Spans are clipped to the tokens they overlap:
       inside a string (value or key), the interior only; over any part of a
       number, the whole token becomes `"<TYPE>"`, quoted, so a phone number
       stored as a number becomes a string; over punctuation, true/false/null
       or whitespace, nothing. Formatting is kept: tokens are located by
       offset, never reserialized. Two masked keys in one object can collide
       on the same placeholder, and the document still parses.
    6. **Replacement** in the original text, with this module's own splicing
       rather than AnonymizerEngine.
    7. **Post-condition** (JSON-aware mode only): json.loads() must accept the
       result, or PiiRedactorError("redaction would produce invalid JSON") is
       raised, fail closed. The message carries no text.

    `entities` lists, sorted, the types of spans that replaced something. A
    span that is dropped entirely was not masked, so it is not reported. (For
    `chat` it is redact()'s list.)

    **Tool-call arguments are never redacted.** In this PRD that holds by
    construction: `Message` has no `tool_calls` field, `normalize_message`
    refuses `tool_calls` (PRD-010), and `redact_for_policy` takes a string.
    The rule is written here, and repeated in the `redact_for_policy`
    docstring, as the contract PRD-016 must keep when it widens `Message`:
    arguments go upstream untouched, and only `content` goes through policy.
    This PRD's JSON-aware mode is what makes a `tool` turn's *result* safe to
    redact once PRD-016 admits it.

    Raises PiiRedactorError when analysis fails and on the JSON post-condition.
    """
    if not settings.PII_REDACTION_ENABLED or not text:
        return RedactionResult(text, [])

    if not policy.structure_safe:
        return RedactionResult(*redact(text))

    analysis = strip_fenced_blocks(text) if policy.skip_fenced_blocks else text
    accepted = _resolve_overlaps(_analyze(analysis, policy))
    if not accepted:
        return RedactionResult(text, [])

    # Only after a span is accepted: text with no PII never pays for json.loads().
    json_tokens = _json_tokens(text) if _is_json_document(text) else None
    ranges = _replacement_ranges(text, analysis, accepted, json_tokens)
    redacted = _splice(text, ranges)
    entities = sorted({entity_type for _, _, _, entity_type in ranges})

    if json_tokens is not None:
        try:
            json.loads(redacted)
        except (ValueError, RecursionError) as exc:
            raise PiiRedactorError("redaction would produce invalid JSON") from exc

    return RedactionResult(redacted, entities)
