"""PRD-012 STORY-013: the code round-trip suite and the latency budget (F11;
Section 11, *MVP definition* and *Benchmark criteria*).

Every case runs the **real** policies, built by `pii_policy.load()` from the
shipped settings, over the checked-in corpora (tests/corpora/pii/):

- AC 1, `code/` under `code`. Each fenced block is byte-identical. Outside
  them, quotes, backslashes, backticks and line breaks keep their count **and
  positions**, and only placeholders differ between them. `.py` still passes
  ast.parse, `.json` json.loads, `.yaml` yaml.safe_load.

  "Positions" means the structural skeleton: `_STRUCTURE.split(text)` gives
  alternating segments and structural characters, and the result must have
  as many segments and the same structural characters, in the same order.
  Masking changes columns, so absolute offsets cannot be the meaning. Line
  numbers and each line's sequence of quotes and backslashes are what code
  syntax depends on, and the skeleton fixes both.
- AC 2, `prose/` under `chat` and `code`: declared entities are masked, except
  the types `code` does not detect, which `_ABSENT_UNDER_CODE` names.
- AC 3, `json/` under `code`: tool results parse, number-token PII is quoted.
- AC 4, `@pytest.mark.benchmark`: `code` p95 at 200,000 characters is under
  STORY-003's budget. Skipped unless `--run-benchmark` (tests/conftest.py):

      pytest tests/test_pii_code_corpus.py -m benchmark --run-benchmark -s

- AC 5, `code/` under `chat`: every file changes, so the corpus is not vacuous.

`chat` cases load `en_core_web_lg` with the shipped settings, through the
tests/test_pii_characterization.py fixture's constants, imported and not
copied. STORY-008's corpus tests (tests/test_pii_structure_safe.py) stay: they
pin STORY-008's ACs, and this module's checks are stronger.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import ast
import json
import re
from typing import Optional

import pytest
import yaml

import app.services.pii_redactor as pii_redactor
import scripts.measure_pii_latency as bench
from app.config import settings
from app.services import pii_policy
from app.services.pattern_detector import strip_fenced_blocks
from app.services.pii_policy import PiiPolicy, get_pii_policy
from app.services.pii_redactor import _RUN_ANCHORS, redact_for_policy
from tests import test_pii_corpus_files as corpus_files
from tests.test_pii_characterization import _LARGE_MODEL_NAME, _SHIPPED_PII_SETTINGS, _model_name

#: The six `code` settings as shipped (app/config.py; STORY-003 fixed the
#: threshold and the limit). Pinned so a developer's .env cannot move them.
_SHIPPED_CODE_SETTINGS = {
    "PII_REDACTION_ENABLED": True,
    "PII_ENTITIES_CODE": "EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE",
    "PII_SCORE_THRESHOLD_CODE": 0.40,
    "PII_CODE_SKIP_CODE_BLOCKS": True,
    "PII_CODE_REDACT_SYSTEM": False,
    "PII_CODE_REDACT_OUTPUT": False,
    "PII_MAX_CHARACTERS_CODE": 200_000,
}

#: The declared prose types `code` does not mask: D7 keeps the NER types out
#: of PII_ENTITIES_CODE, so a name in prose under `code` is not masked (PRD
#: Section 6.4). Listed by name so that a corpus or settings change has to
#: update it on purpose.
_ABSENT_UNDER_CODE = frozenset({"PERSON"})

#: A quote, a backtick, a line break or a backslash, kept as a separator.
_STRUCTURE = re.compile(r'(\\|["\'`\r\n])')
_PLACEHOLDER = re.compile(r"<([A-Z_]+)>")

_BENCHMARK_SIZE = 200_000
#: STORY-003's n.
_BENCHMARK_RUNS = 20


@pytest.fixture(autouse=True)
def _shipped_code_settings(monkeypatch):
    for name, value in _SHIPPED_CODE_SETTINGS.items():
        monkeypatch.setattr(settings, name, value)
    # tests/conftest.py restores `_policies` after the test.
    pii_policy.load()
    yield


@pytest.fixture
def _shipped_chat(monkeypatch) -> PiiPolicy:
    """`chat` as shipped: tests/test_pii_characterization.py's settings, on en_core_web_lg."""
    for name, value in _SHIPPED_PII_SETTINGS.items():
        monkeypatch.setattr(settings, name, value)
    cached = pii_redactor._analyzer
    if cached is not None and _model_name(cached) != _LARGE_MODEL_NAME:
        monkeypatch.setattr(pii_redactor, "_analyzer", None)
    assert _model_name(pii_redactor._get_analyzer()) == _LARGE_MODEL_NAME
    pii_policy.load()
    return get_pii_policy("chat")


def _code() -> PiiPolicy:
    return get_pii_policy("code")


def _fenced_blocks(text: str) -> list[tuple[int, int]]:
    """(start, end) of each fenced block, delimiters included.

    strip_fenced_blocks turns every fenced character into a newline, so the
    positions that differ are the fenced ones except the block's own newlines.
    Differing positions separated only by newlines belong to one block.
    """
    blanked = strip_fenced_blocks(text)
    blocks: list[list[int]] = []
    for i, (original, blank) in enumerate(zip(text, blanked)):
        if original == blank:
            continue
        if blocks and not text[blocks[-1][1]:i].strip("\n"):
            blocks[-1][1] = i + 1
        else:
            blocks.append([i, i + 1])
    return [(start, end) for start, end in blocks]


def _masked_runs(original: str, result: str) -> Optional[list[tuple[str, str]]]:
    """[(entity, original text)] for each placeholder in `result`, or None when
    `result` is not `original` with some non-empty runs replaced by placeholders."""
    parts = _PLACEHOLDER.split(result)
    # split() alternates literal text and captured entity names.
    pattern = "".join("(.+?)" if i % 2 else re.escape(part) for i, part in enumerate(parts))
    match = re.fullmatch(pattern, original, re.DOTALL)
    if match is None:
        return None
    return list(zip(parts[1::2], match.groups()))


def _redacted(path) -> tuple[str, str]:
    text = corpus_files._read(path)
    return text, redact_for_policy(text, _code()).text


def _of_suffix(suffix: str) -> list:
    return [p for p in corpus_files._CODE_FILES if p.suffix == suffix]


_CODE = corpus_files._CODE_FILES
_CODE_IDS = corpus_files._ids(corpus_files._CODE_FILES)


# --- AC 1: code/ round-trips under `code` -------------------------------------


@pytest.mark.parametrize("path", _CODE, ids=_CODE_IDS)
def test_every_fenced_block_is_byte_identical(path):
    text, result = _redacted(path)

    assert [result[s:e] for s, e in _fenced_blocks(result)] == [text[s:e] for s, e in _fenced_blocks(text)]


def test_the_code_corpus_has_several_fenced_blocks():
    """Guards the test above against passing vacuously."""
    blocks = [text[s:e] for text in map(corpus_files._read, _CODE) for s, e in _fenced_blocks(text)]

    assert len(blocks) >= 2
    assert any(block.lstrip(" ").startswith("~~~") for block in blocks)
    assert any(block.lstrip(" ").startswith("```") for block in blocks)


@pytest.mark.parametrize("path", _CODE, ids=_CODE_IDS)
def test_structural_characters_keep_their_count_and_positions(path):
    text, result = _redacted(path)
    original_parts, result_parts = _STRUCTURE.split(text), _STRUCTURE.split(result)

    assert len(result_parts) == len(original_parts)
    assert result_parts[1::2] == original_parts[1::2]


@pytest.mark.parametrize("path", _CODE, ids=_CODE_IDS)
def test_only_placeholders_change_between_structural_characters(path):
    text, result = _redacted(path)

    for original, masked in zip(_STRUCTURE.split(text)[0::2], _STRUCTURE.split(result)[0::2]):
        if original != masked:
            assert _masked_runs(original, masked) is not None, (original, masked)


@pytest.mark.parametrize("path", _CODE, ids=_CODE_IDS)
def test_every_masked_run_holds_its_entity_anchor(path):
    """STORY-013 F-1, independent of any parser: a masked email run holds its
    `@`, a masked number run a digit. `email='...'` used to mask `email`."""
    text, result = _redacted(path)

    for original, masked in zip(_STRUCTURE.split(text)[0::2], _STRUCTURE.split(result)[0::2]):
        for entity, run in _masked_runs(original, masked) or []:
            if entity in _RUN_ANCHORS:
                assert _RUN_ANCHORS[entity](run), (entity, run)


@pytest.mark.parametrize("path", _CODE, ids=_CODE_IDS)
def test_every_code_sample_is_masked_under_code(path):
    """Guards the checks above: each file has something masked outside its fences."""
    assert redact_for_policy(corpus_files._read(path), _code()).entities


def test_the_code_corpus_has_python_json_and_yaml_samples():
    assert _of_suffix(".py") and _of_suffix(".json") and _of_suffix(".yaml")


@pytest.mark.parametrize("path", _of_suffix(".py"), ids=corpus_files._ids(_of_suffix(".py")))
def test_every_python_sample_still_parses(path):
    ast.parse(_redacted(path)[1], filename=str(path))


@pytest.mark.parametrize("path", _of_suffix(".json"), ids=corpus_files._ids(_of_suffix(".json")))
def test_every_json_code_sample_still_parses(path):
    json.loads(_redacted(path)[1])


@pytest.mark.parametrize("path", _of_suffix(".yaml"), ids=corpus_files._ids(_of_suffix(".yaml")))
def test_every_yaml_sample_still_loads(path):
    """Beyond the AC: PyYAML is already a dependency, and YAML is in the corpus."""
    yaml.safe_load(_redacted(path)[1])


# --- AC 2: prose/ masked under both profiles ----------------------------------


def _prose(path) -> str:
    """The sample without its `# expect:` header, which is metadata, not user text."""
    return corpus_files._read(path).partition("\n")[2]


_PROSE = corpus_files._PROSE_FILES
_PROSE_IDS = corpus_files._ids(corpus_files._PROSE_FILES)


def test_the_types_code_does_not_mask_are_enumerated():
    declared = {entity for path in _PROSE for entity in corpus_files._declared(path)}

    assert declared - set(_code().entities) == _ABSENT_UNDER_CODE


@pytest.mark.parametrize("path", _PROSE, ids=_PROSE_IDS)
def test_prose_declared_entities_are_masked_under_code(path):
    expected = set(corpus_files._declared(path)) - _ABSENT_UNDER_CODE
    assert expected, "a prose sample with nothing `code` masks would pass vacuously"

    result = redact_for_policy(_prose(path), _code())

    assert expected <= set(result.entities)
    for entity in expected:
        assert f"<{entity}>" in result.text, entity


@pytest.mark.parametrize("path", _PROSE, ids=_PROSE_IDS)
def test_prose_declared_entities_are_masked_under_chat(path, _shipped_chat):
    expected = set(corpus_files._declared(path))

    result = redact_for_policy(_prose(path), _shipped_chat)

    assert expected <= set(result.entities)
    for entity in expected:
        assert f"<{entity}>" in result.text, entity


# --- AC 5: the code corpus is not vacuous --------------------------------------


@pytest.mark.parametrize("path", _CODE, ids=_CODE_IDS)
def test_chat_changes_every_code_sample(path, _shipped_chat):
    """Today's `chat` masks identifiers and literals in every code sample: the
    corpus holds what `code` exists to leave alone (the PRD-011 Risk 5 /
    STORY-011 "not vacuous" precedent)."""
    text = corpus_files._read(path)

    result = redact_for_policy(text, _shipped_chat).text

    assert result != text
    assert set(_PLACEHOLDER.findall(result)) - set(_PLACEHOLDER.findall(text))


# --- AC 3: json/ tool results under `code` -------------------------------------


_JSON = corpus_files._JSON_FILES
_JSON_IDS = corpus_files._ids(corpus_files._JSON_FILES)


def test_code_redacts_tool_turns():
    """`json/` holds tool results. Step 0 still refuses `tool` turns, so they are
    tested by direct call to redact_for_policy (PRD Section 6.3); the policy
    must list the role for that to be the path PRD-016 opens."""
    assert "tool" in _code().input_roles


@pytest.mark.parametrize("path", _JSON, ids=_JSON_IDS)
def test_every_json_tool_result_parses_after_redaction(path):
    result = redact_for_policy(corpus_files._read(path), _code())

    json.loads(result.text)
    assert result.entities


def _leaves(value):
    """Scalar values in document order, keys ignored (masking may rename keys)."""
    if isinstance(value, dict):
        for item in value.values():
            yield from _leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from _leaves(item)
    else:
        yield value


def _is_pii_number(value) -> bool:
    """A number token of a corpus PII class (SOURCES.md): a 555-01xx phone or a
    Luhn-valid card. `order_number: 4000813378` is neither."""
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return bool(corpus_files._PHONE_555.search(str(value))) or (
        13 <= len(str(value)) <= 19 and corpus_files._luhn(value)
    )


_JSON_WITH_NUMBER_PII = [
    path for path in _JSON if any(_is_pii_number(v) for v in _leaves(json.loads(corpus_files._read(path))))
]


def test_the_json_corpus_has_number_token_pii():
    """Guards the test below against passing vacuously."""
    assert _JSON_WITH_NUMBER_PII


@pytest.mark.parametrize("path", _JSON_WITH_NUMBER_PII, ids=corpus_files._ids(_JSON_WITH_NUMBER_PII))
def test_number_token_pii_is_quoted(path):
    original = list(_leaves(json.loads(corpus_files._read(path))))

    result = list(_leaves(json.loads(redact_for_policy(corpus_files._read(path), _code()).text)))

    assert len(result) == len(original)
    for before, after in zip(original, result):
        if _is_pii_number(before):
            assert after in ("<PHONE_NUMBER>", "<CREDIT_CARD>"), (before, after)


def test_escape_adjacent_pii_is_masked_and_the_escape_kept():
    """STORY-008 finding M1: default-entity PII right after `\\n`, `\\t`, `\\"`.

    The IBAN and the card were missed before STORY-013 F-4: the analyzer read
    `\\nGB82` as `nGB82` and `\\t4111` as `t4111`."""
    text = corpus_files._read(corpus_files._PII / "json" / "build-log-escapes.json")

    result = redact_for_policy(text, _code()).text

    json.loads(result)
    assert "jane.doe@example.com" in text and "jane.doe@example.com" not in result
    for masked in (
        "\\n<EMAIL_ADDRESS>",
        "\\t<PHONE_NUMBER>",
        '\\"<EMAIL_ADDRESS>\\"',
        "\\n<IBAN_CODE>",
        "\\t<CREDIT_CARD>",
    ):
        assert masked in result, masked


# --- AC 4: the latency budget --------------------------------------------------


@pytest.mark.benchmark
def test_code_p95_at_200k_is_within_the_story_003_budget(capsys):
    """`code` p95 over STORY-003's agent-shaped 200,000-character conversation,
    step 6 as run_conversation does it (bench._redact_policy_roles), after one
    discarded warm run. The budget is bench.CODE_P95_BUDGET_MS."""
    policy = _code()
    conversation = bench._conversation(_BENCHMARK_SIZE)
    assert sum(len(m.content) for m in conversation) == _BENCHMARK_SIZE

    bench._redact_policy_roles(policy, conversation)
    samples = bench._sample("code", _BENCHMARK_RUNS, lambda: bench._redact_policy_roles(policy, conversation))
    minimum, p50, p95 = samples.summary()

    line = (
        f"STORY-013 code p95 at {_BENCHMARK_SIZE} chars: {p95:.2f} ms "
        f"(min {minimum:.2f}, p50 {p50:.2f}, n={samples.n}; budget {bench.CODE_P95_BUDGET_MS} ms)"
    )
    with capsys.disabled():
        print("\n" + line)
    assert p95 < bench.CODE_P95_BUDGET_MS, line
