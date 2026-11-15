"""`yaml.safe_load`, plus a startup error for a key written twice (PRD-016 Section 6.6, D13).

PyYAML resolves duplicate mapping keys silently, last one winning, so a config
file with `lists:` or `rules:` written twice loses one whole section with no
error -- and what is enforced changes without anyone being told. This module is
the shared strict loader `pattern_config.load()`'s docstring asked for once a
second YAML config arrived: `pattern_config` (PRD-016 STORY-005) and
`action_config` (STORY-007) both parse through `safe_load` below.

It stays a `yaml.SafeLoader` subclass, so the `!!python/...` tags are refused
exactly as `yaml.safe_load` refuses them, and a document with no duplicate
returns exactly what `yaml.safe_load` returns. A duplicate raises
`yaml.constructor.ConstructorError`, a `yaml.YAMLError`, so a caller's existing
`except yaml.YAMLError` arm keeps catching it.

Pure on purpose: no settings, no I/O, and no `app` import. The caller reads the
file and maps the error to its own exception, which names the file.
"""

from typing import Any

import yaml

# `<<` merge keys are skipped by the duplicate check: overriding a merged key
# (`<<: *base` then `k: 2`) is YAML's documented merge semantics, not a
# duplicate, and `SafeConstructor.flatten_mapping` resolves it. Skipping them
# keeps the result identical to `yaml.safe_load` for such a document.
_MERGE_TAG = "tag:yaml.org,2002:merge"


class _StrictSafeLoader(yaml.SafeLoader):
    """A `SafeLoader` whose mappings refuse a key written twice, at any depth."""

    def construct_mapping(self, node, deep=False):
        # The explicit keys are checked before `super()` runs `flatten_mapping`,
        # which prepends the merged keys to `node.value`. `construct_object`
        # caches by node, so building a key here and again in `super()`
        # constructs it once. `!!set` also goes through `construct_mapping`,
        # so `!!set {a, a}` is refused too -- acceptable: a member written
        # twice is just as likely a mistake (STORY-005 decision).
        if isinstance(node, yaml.MappingNode):
            seen: dict[Any, yaml.Mark] = {}
            for key_node, _ in node.value:
                if key_node.tag == _MERGE_TAG:
                    continue
                key = self.construct_object(key_node, deep=deep)
                try:
                    hash(key)
                except TypeError:
                    continue  # super() raises its own "found unhashable key"
                if key in seen:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        f"found duplicate key {key!r} (first defined on line {seen[key].line + 1})",
                        key_node.start_mark,
                    )
                seen[key] = key_node.start_mark
        return super().construct_mapping(node, deep=deep)


def safe_load(text: str) -> Any:
    """Parse `text` as `yaml.safe_load` does, refusing a duplicate mapping key.

    Raises `yaml.YAMLError` (a `ConstructorError`) on a key written twice in
    any mapping, at any depth; the message names the key, the line it was first
    defined on and the line of the second definition. Keys that compare equal
    in Python count as one (`a` and `"a"`, `1` and `1.0`), since `yaml.safe_load`
    would collapse them into one and drop a value silently. Otherwise returns
    exactly what `yaml.safe_load(text)` returns.
    """
    return yaml.load(text, Loader=_StrictSafeLoader)  # noqa: S506 -- a SafeLoader subclass
