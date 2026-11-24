"""`json.loads`, plus a refusal for a key written twice (PRD-023 Section 9.2, T7).

`json.loads` resolves a duplicate object key silently, the last one winning. On
the `/mcp` ingress that is a smuggling vector: `{"method": "tools/list", "method":
"tools/call"}` could be read one way by a proxy or a log line and another by the
handler. This is the JSON sibling of `strict_yaml`: the same rule, at any depth.

`NaN`, `Infinity` and `-Infinity` are refused too: they are not JSON, and a
parameter that is not a number must not reach a policy decision as a float.

Pure on purpose: no settings, no I/O, and no `app` import. A caller catches
`ValueError` (`json.JSONDecodeError` is one) and `RecursionError` (a body nested
deeper than the interpreter allows) and maps both to its own error.
"""

import json
from typing import Any, List, Tuple


def _no_duplicates(pairs: List[Tuple[str, Any]]) -> dict:
    """The object hook: a dict of the pairs, or ValueError on a repeated key."""
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _refuse_constant(name: str) -> Any:
    raise ValueError(f"{name} is not valid JSON")


def loads(text: str) -> Any:
    """Parse `text` as JSON, refusing a duplicate object key at any depth."""
    return json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_refuse_constant)
