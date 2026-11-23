"""`app/services/strict_json.py`: JSON that refuses a key written twice (PRD-023 T7, STORY-011)."""

import pytest

from app.services import strict_json


def test_a_valid_document_loads_like_json_loads():
    text = '{"a": [1, 2.5, "x", null, true], "b": {"c": {}}}'
    assert strict_json.loads(text) == {"a": [1, 2.5, "x", None, True], "b": {"c": {}}}


def test_a_top_level_duplicate_key_is_refused():
    with pytest.raises(ValueError, match="duplicate key 'a'"):
        strict_json.loads('{"a": 1, "a": 2}')


def test_a_nested_duplicate_key_is_refused():
    with pytest.raises(ValueError, match="duplicate key 'x'"):
        strict_json.loads('{"a": [{"b": {"x": 1, "x": 1}}]}')


def test_the_same_key_in_sibling_objects_is_fine():
    assert strict_json.loads('[{"a": 1}, {"a": 2}]') == [{"a": 1}, {"a": 2}]


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_json_constants_are_refused(constant):
    with pytest.raises(ValueError):
        strict_json.loads('{"a": %s}' % constant)


def test_malformed_json_raises_a_value_error():
    with pytest.raises(ValueError):
        strict_json.loads("{not json")


def test_deep_nesting_raises_recursion_error_or_value_error():
    with pytest.raises((RecursionError, ValueError)):
        strict_json.loads("[" * 100000)
