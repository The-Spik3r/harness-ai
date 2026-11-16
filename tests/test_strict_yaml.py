"""PRD-016 STORY-005: `strict_yaml`, the shared loader that refuses a duplicate key.

PRD-016 Section 6.6 and D13: PyYAML keeps the last of two equal keys silently,
so a second `lists:` or `rules:` section vanishes with no error. `strict_yaml`
is `yaml.safe_load` plus that one refusal. The cases below pin the three
halves of the contract: a duplicate at any depth is a `yaml.YAMLError` naming
the key and its lines (AC 2); a document without one parses exactly as
`yaml.safe_load` parses it (AC 2); and the `!!python/...` tags are refused as
`yaml.safe_load` refuses them (AC 3).

The module is pure and imports nothing from `app.config`, so no environment
defaults are set here.
"""

import inspect
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import app.services.strict_yaml as strict_yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]


# --- AC 2: a duplicate key is refused ---------------------------------------


def test_a_duplicate_top_level_key_is_refused_naming_the_key_and_its_line():
    with pytest.raises(yaml.YAMLError) as exc_info:
        strict_yaml.safe_load("a: 1\na: 2\n")

    message = str(exc_info.value)
    assert "duplicate key 'a'" in message
    assert "first defined on line 1" in message
    assert "line 2" in message, "the message must point at the second definition"


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("x:\n  b: 1\n  b: 2\n", "b"),
        ("- {c: 1, c: 2}\n", "c"),
        ("one:\n  two:\n    three:\n      d: 1\n      d: 2\n", "d"),
        ("lists:\n  - patterns: [x]\n    patterns: [y]\n", "patterns"),
    ],
    ids=["block-nested", "flow-in-sequence", "three-levels-deep", "mapping-in-sequence"],
)
def test_a_nested_duplicate_key_is_refused(text, key):
    with pytest.raises(yaml.YAMLError) as exc_info:
        strict_yaml.safe_load(text)

    assert f"duplicate key '{key}'" in str(exc_info.value)


@pytest.mark.parametrize(
    "text",
    ['a: 1\n"a": 2\n', "1: x\n1.0: y\n"],
    ids=["quoted-and-plain", "int-and-float"],
)
def test_equal_but_differently_spelled_keys_are_duplicates(text):
    """Both pairs collapse into one Python dict key under `yaml.safe_load`,
    which is exactly the silent loss D13 forbids."""
    assert len(yaml.safe_load(text)) == 1, "precondition: safe_load drops one"

    with pytest.raises(yaml.YAMLError, match="duplicate key"):
        strict_yaml.safe_load(text)


def test_the_error_is_a_yaml_error_so_callers_keep_their_except_arm():
    with pytest.raises(yaml.YAMLError) as exc_info:
        strict_yaml.safe_load("a: 1\na: 2\n")

    assert isinstance(exc_info.value, yaml.constructor.ConstructorError)
    assert issubclass(type(exc_info.value), yaml.YAMLError)


# --- AC 2: no duplicate, the same result as yaml.safe_load ------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "just a string\n",
        "42\n",
        "a: 1\nb: [1, 2, {c: 3}]\nd: {e: {f: null}}\n",
        "a: {k: 1}\nb: {k: 2}\n",
        "- k: 1\n- k: 2\n",
        "base: &b {k: 1, j: 2}\nalias: *b\n",
        "base: &b {k: 1}\nd:\n  <<: *b\n  k: 2\n",
        "a: &b {k: 1}\nc: &d {j: 2}\ne:\n  <<: [*b, *d]\n  j: 3\n",
        "!!set {a, b}\n",
    ],
    ids=[
        "empty",
        "bare-string",
        "scalar",
        "nested-maps-and-lists",
        "same-key-in-sibling-mappings",
        "same-key-in-sibling-list-items",
        "anchor-and-alias",
        "merge-with-override",
        "merge-list-with-override",
        "set",
    ],
)
def test_without_duplicates_the_result_equals_yaml_safe_load(text):
    assert strict_yaml.safe_load(text) == yaml.safe_load(text)


def test_the_example_patterns_file_parses_as_yaml_safe_load_parses_it():
    """The repo's shipped file is duplicate-free, so adopting the strict
    loader in `pattern_config` changes nothing for it."""
    text = (_REPO_ROOT / "examples" / "patterns.yaml").read_text(encoding="utf-8")

    assert strict_yaml.safe_load(text) == yaml.safe_load(text)


# --- AC 3: the !!python tags stay refused -----------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "!!python/object:os.system {}\n",
        '!!python/object/apply:os.system ["echo"]\n',
        "!!python/name:os.system\n",
    ],
    ids=["object", "object-apply", "name"],
)
def test_python_tags_are_refused_as_safe_load_refuses_them(text):
    with pytest.raises(yaml.constructor.ConstructorError) as safe_exc:
        yaml.safe_load(text)
    with pytest.raises(yaml.constructor.ConstructorError) as strict_exc:
        strict_yaml.safe_load(text)

    assert "could not determine a constructor" in str(strict_exc.value)
    assert str(strict_exc.value) == str(safe_exc.value)


# --- purity -----------------------------------------------------------------


def test_strict_yaml_stays_pure():
    """No settings, no file I/O and no `app` import (brief: pure modules)."""
    source = inspect.getsource(strict_yaml)

    assert "settings" not in vars(strict_yaml)
    assert "open(" not in source
    assert "Path(" not in source
    assert "os." not in source
    imports = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    assert not [line for line in imports if re.match(r"(from|import) app(\.|\s|$)", line)]


def test_importing_strict_yaml_loads_no_settings():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, app.services.strict_yaml; "
            "print(sorted(m for m in sys.modules if m == 'app' or m.startswith('app.')))",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == str(["app", "app.services", "app.services.strict_yaml"])
