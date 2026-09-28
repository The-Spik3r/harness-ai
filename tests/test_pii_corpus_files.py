"""PRD-012 STORY-001: the PII corpora load -- code, prose and JSON samples as checked-in files.

The corpora behind PRD-012's claims about false positives and masked PII
(PRD-012 Sections 4 *Corpora*, 7/F11, 11 *MVP definition*). Every sample is a
checked-in file under `tests/corpora/pii/`, discovered from disk: adding a
sample needs no edit here, and an empty directory fails the guard tests
instead of parametrizing to nothing (an empty parameter set is a skip, and a
skip passes).

**This module asserts nothing about redaction.** It proves only that the files
exist, parse, hold the cases the story names and declare what they contain.
STORY-003 counts false positives and times redaction over them; STORY-008 and
STORY-013 assert redaction behaviour. Those modules may import the discovery
lists and `_declared` from here (the `tests.test_pattern_characterization`
import precedent) rather than re-deriving them.

Line 1 of every `prose/` sample is a header, the PRD-011 `injections/`
convention:

    # expect: EMAIL_ADDRESS, PHONE_NUMBER, PERSON

It names the entity types **present** in the file -- a lower bound, not an
exact set, and not "what every profile masks". Under `code`, `PERSON` is off by
default (PRD-012 D7), so consumers assert `declared & policy.entities <= found`,
never `declared <= found`.

All data is synthetic; `tests/corpora/pii/SOURCES.md` records where each class
of value comes from, and one test here holds every email to the reserved
`example.com` / `example.org` domains.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import ast
import json
import re
from pathlib import Path
from typing import Any, Iterator, Optional

import pytest

from app.services.pattern_detector import strip_code_spans

_PII = Path(__file__).resolve().parent / "corpora" / "pii"

#: Metadata, not samples. Excluded by name so a new sample needs no test edit.
_NOT_SAMPLES = frozenset({"SOURCES.md"})


def _corpus(group: str) -> list[Path]:
    """Every sample in `tests/corpora/pii/<group>/`, sorted, metadata excluded.

    A missing directory raises at collection, which is a loud failure.
    """
    return sorted(
        path
        for path in (_PII / group).iterdir()
        if path.is_file() and path.name not in _NOT_SAMPLES and not path.name.startswith(".")
    )


def _read(path: Path) -> str:
    # No newline normalisation: the test sees the bytes a client would send.
    return path.read_text(encoding="utf-8")


def _ids(paths: list[Path]) -> list[str]:
    return [path.name for path in paths]


_CODE_FILES = _corpus("code")
_PROSE_FILES = _corpus("prose")
_JSON_FILES = _corpus("json")
_ALL_SAMPLES = _CODE_FILES + _PROSE_FILES + _JSON_FILES
_ALL_JSON = [p for p in _CODE_FILES if p.suffix == ".json"] + _JSON_FILES
_ALL_PY = sorted(_PII.rglob("*.py"))

#: The Presidio entity names the harness configures (app/config.py, PII_ENTITIES).
#: Closed: a header naming anything else fails, so a typo cannot make a file
#: silently declare nothing.
_KNOWN_ENTITIES = frozenset(
    {"PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN", "IBAN_CODE", "LOCATION"}
)
_REQUIRED_PROSE_ENTITIES = frozenset({"EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "IBAN_CODE", "PERSON"})
#: The NER-backed types; a file declaring only these is vacuous under `code` (D7).
_NER_ENTITIES = frozenset({"PERSON", "LOCATION"})

_HEADER_FORMAT = "# expect: <ENTITY>, <ENTITY>, ..."
#: `\s*$` absorbs the CR of a CRLF checkout.
_HEADER = re.compile(r"^# expect: (?P<entities>[A-Z_]+(?:, [A-Z_]+)*)\s*$")

_EMAIL = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
_SYNTHETIC_DOMAINS = ("example.com", "example.org")
#: 555-01xx, separated (`555-0134`, `555 0134`, `555.0134`) or packed (`4155550134`).
_PHONE_555 = re.compile(r"555[-. ]?01\d\d|\d{3}55501\d\d")
#: The invented cast (SOURCES.md). Every code sample names at least one.
_CAST = (
    "Jane Doe",
    "Patrick O'Brien",
    "Maria Lopez",
    "Priya Raghunathan",
    "Kenji Watanabe",
    "Aisha Bello",
    "Tomás Herrera",
    "Zoë Müller-Schmidt",
)
#: Lines, not characters: "a few hundred lines" is the target; this is the floor.
_MIN_NON_BLANK_LINES = 150
_REQUIRED_CODE_SUFFIXES = (".java", ".ts", ".py", ".yaml", ".json", ".md")
#: The source languages AC 2's string-literal cases must appear in.
_STRING_LITERAL_SUFFIXES = (".java", ".ts", ".py")

#: Any line that opens or closes a fence, per PRD-011's parser
#: (`app/services/pattern_detector.py`, `_FENCE_OPEN`).
_FENCE_LINE = re.compile(r"^ {0,3}(?:`{3,}|~{3,})[^\n]*$", re.MULTILINE)


def _declared(path: Path) -> Optional[tuple[str, ...]]:
    """The prose header's entities, in file order; None when line 1 is not a valid header."""
    first, _, _ = _read(path).partition("\n")
    match = _HEADER.match(first)
    return tuple(match["entities"].split(", ")) if match else None


def _walk(value: Any, depth: int = 0) -> Iterator[tuple[str, Optional[str], Any, int]]:
    """Every node of a parsed JSON document as (kind, key, value, depth); kind is 'key' or 'value'."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield "key", key, key, depth
            yield from _walk(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child, depth + 1)
    else:
        yield "value", None, value, depth


def _luhn(number: int) -> bool:
    digits = [int(d) for d in str(number)][::-1]
    total = sum(d if i % 2 == 0 else (d * 2 - 9 if d > 4 else d * 2) for i, d in enumerate(digits))
    return total % 10 == 0


def _of_suffix(suffix: str) -> list[Path]:
    return [p for p in _CODE_FILES if p.suffix == suffix]


def _ends_inside_a_fence(text: str) -> bool:
    """The text ends inside a fence that is never closed.

    The last fence-like line is followed by content, and all of that content is
    blanked by PRD-011's parser. A fence closed at end of file has nothing after
    its closer; a closer followed by prose leaves that prose unblanked.
    """
    fences = list(_FENCE_LINE.finditer(text))
    if not fences:
        return False
    tail_start = fences[-1].end()
    return text[tail_start:].strip() != "" and strip_code_spans(text)[tail_start:].strip() == ""


# --- AC 1: the code corpus holds every required kind of file -----------------


def test_the_code_corpus_holds_every_required_kind_of_file():
    assert _CODE_FILES, "tests/corpora/pii/code/ is empty"

    for suffix in _REQUIRED_CODE_SUFFIXES:
        assert _of_suffix(suffix), f"no {suffix} sample in tests/corpora/pii/code/"

    for path in _CODE_FILES:
        text = _read(path)
        if path.suffix != ".md":
            lines = [line for line in text.splitlines() if line.strip()]
            assert len(lines) >= _MIN_NON_BLANK_LINES, f"{path.name}: {len(lines)} lines, a toy"
        assert _EMAIL.search(text), f"{path.name}: no example email"
        assert _PHONE_555.search(text), f"{path.name}: no 555-01xx phone-shaped number"
        assert any(name in text for name in _CAST), f"{path.name}: no cast name"


def test_the_code_corpus_mixes_fenced_and_unfenced_code_in_markdown():
    def qualifies(text: str) -> bool:
        backtick = re.search(r"^ {0,3}```", text, re.MULTILINE)
        tilde = re.search(r"^ {0,3}~~~", text, re.MULTILINE)
        raw = len(_EMAIL.findall(text))
        outside = len(_EMAIL.findall(strip_code_spans(text)))
        # Emails both inside a fence and in the prose around it.
        return bool(backtick and tilde) and 0 < outside < raw

    assert any(qualifies(_read(p)) for p in _of_suffix(".md")), (
        "no .md sample with both ``` and ~~~ fences and PII inside and outside them"
    )


# --- AC 2: the named edge cases ----------------------------------------------


def test_the_code_corpus_has_an_apostrophe_name():
    assert any("O'Brien" in _read(p) for p in _CODE_FILES), "no code sample with O'Brien"


def test_the_code_corpus_has_pii_against_its_quotes():
    against_quotes = re.compile(r"[\"'][\w.+-]+@example\.(?:com|org)[\"']")
    for suffix in _STRING_LITERAL_SUFFIXES:
        assert any(against_quotes.search(_read(p)) for p in _of_suffix(suffix)), (
            f"no {suffix} sample with an email right against its quotes"
        )


def test_the_code_corpus_has_an_escaped_quote_and_a_backslash_path():
    windows_path = re.compile(r"[A-Za-z]:\\\\")  # a literal `C:\\` inside a string
    for suffix in _STRING_LITERAL_SUFFIXES:
        texts = [_read(p) for p in _of_suffix(suffix)]
        assert any('\\"' in t for t in texts), f"no {suffix} sample with an escaped quote"
        assert any(windows_path.search(t) for t in texts), f"no {suffix} sample with a backslash path"


def test_the_code_corpus_has_an_unterminated_fence():
    assert any(_ends_inside_a_fence(_read(p)) for p in _of_suffix(".md")), (
        "no .md sample ending inside an unterminated fence"
    )


# --- AC 3: every prose sample declares its entities --------------------------


@pytest.mark.parametrize("path", _PROSE_FILES, ids=_ids(_PROSE_FILES))
def test_every_prose_sample_declares_its_entities(path):
    # Parametrized over files, not parsed headers, so a bad header fails
    # rather than dropping the file out of the suite.
    declared = _declared(path)
    first = _read(path).partition("\n")[0]
    assert declared is not None, f"{path.name}: line 1 is not {_HEADER_FORMAT!r} (got {first[:80]!r})"

    unknown = sorted(set(declared) - _KNOWN_ENTITIES)
    assert not unknown, f"{path.name}: unknown entity types {unknown}"
    assert len(declared) == len(set(declared)), f"{path.name}: duplicate entity types in the header"
    assert set(declared) - _NER_ENTITIES, (
        f"{path.name}: declares only NER types, which the default `code` profile never detects"
    )


def test_the_prose_corpus_covers_the_required_entities():
    assert _PROSE_FILES, "tests/corpora/pii/prose/ is empty"
    covered = {entity for path in _PROSE_FILES for entity in (_declared(path) or ())}
    missing = sorted(_REQUIRED_PROSE_ENTITIES - covered)
    assert not missing, f"no prose sample declares {missing}"


# --- AC 4: every JSON sample parses, and together they cover the shapes -----


@pytest.mark.parametrize("path", _ALL_JSON, ids=_ids(_ALL_JSON))
def test_every_json_sample_parses(path):
    try:
        json.loads(_read(path))
    except json.JSONDecodeError as exc:
        pytest.fail(f"{path.name}: does not parse: {exc.msg} at line {exc.lineno}, column {exc.colno}")


def test_the_json_corpus_covers_strings_keys_numbers_nesting_and_escapes():
    assert _JSON_FILES, "tests/corpora/pii/json/ is empty"
    texts = [_read(p) for p in _JSON_FILES]
    nodes = [node for text in texts for node in _walk(json.loads(text))]

    values = [value for kind, _, value, _ in nodes if kind == "value"]
    keys = [key for kind, key, _, _ in nodes if kind == "key"]
    # bool is an int subclass; a JSON `true` is never a phone or a card.
    integers = [v for v in values if isinstance(v, int) and not isinstance(v, bool)]

    assert any(isinstance(v, str) and _EMAIL.search(v) for v in values), "no email in a string value"
    assert any(_EMAIL.search(k) for k in keys), "no email in a key"
    assert any(_PHONE_555.search(str(n)) for n in integers), "no phone as a JSON number token"
    assert any(13 <= len(str(n)) <= 19 and _luhn(n) for n in integers), "no card number as a JSON number token"
    assert max(depth for *_, depth in nodes) >= 3, "no document nested three levels deep"
    assert any("\\\\" in t for t in texts), "no \\\\ escape inside a string"
    assert any('\\"' in t for t in texts), 'no \\" escape inside a string'


# --- AC 5: every Python sample parses ----------------------------------------


def test_the_corpus_holds_a_python_sample():
    assert _ALL_PY, "no .py sample under tests/corpora/pii/"


@pytest.mark.parametrize("path", _ALL_PY, ids=_ids(_ALL_PY))
def test_every_python_sample_parses(path):
    ast.parse(_read(path), filename=str(path))


def test_no_corpus_python_file_is_collectable_as_a_test():
    # No pytest config narrows collection, so a sample named like a test
    # would be imported and run as one.
    collectable = [p.name for p in _ALL_PY if re.fullmatch(r"test_.*\.py|.*_test\.py", p.name)]
    assert not collectable, f"corpus files pytest would collect: {collectable}"


# --- synthetic data and provenance -------------------------------------------


def test_every_email_in_the_corpus_is_on_a_reserved_domain():
    def reserved(domain: str) -> bool:
        domain = domain.lower()
        return any(domain == d or domain.endswith("." + d) for d in _SYNTHETIC_DOMAINS)

    # File and domain only -- never the address.
    offending = sorted(
        {(p.name, domain) for p in _ALL_SAMPLES for domain in _EMAIL.findall(_read(p)) if not reserved(domain)}
    )
    assert not offending, f"emails outside example.com / example.org: {offending}"


def test_sources_names_every_sample():
    sources = _PII / "SOURCES.md"
    assert sources.is_file(), "tests/corpora/pii/SOURCES.md is missing"
    provenance = _read(sources)
    for path in _ALL_SAMPLES:
        assert f"`{path.name}`" in provenance, f"{path.name} has no provenance in SOURCES.md"
