"""The action decision audit: `ActionDecision`s in, `action_decisions` rows out (PRD-016 Sections 4, 6.10, 6.12, F10, D8).

The I/O edge (Section 6.12). The engine (`action_policy`), the adapters and the
classifiers stay pure; every database write the action audit makes is here,
through `app.db.database.insert_action_decisions`. PRD-017 is the first live
caller of `record()`: `query_pipeline` step 8 calls it after the success row,
with that row's `audit_id` (STORY-010).

What each column holds, for decision `d` and identity `i`:

- `timestamp`: one UTC timestamp per `record()` call, shared by every row.
- `audit_id`, `session_id`: as given; `None` stores NULL (a direct call has
  no audit row).
- `user_id`, `role`: `i.user_id`, `i.role`.
- `tool_call_id`, `tool_name`, `decision`, `rule`, `reason`, `granted_by`,
  `policy_digest`: copied from `d`. `reason` is stored by orchestrator
  decision (STORY-014 plan; PRD 6.10 amended).
- `operation_kind`: the reported operation's kind; NULL when there is none
  (`tool.unknown`, `tool.malformed`, `tool.opaque`, the fail-closed path).
- `target_preview`: the reported operation's target -- what the rule judged
  (Section 6.10), not `operations[0]` -- redacted (below), then cut to 500.
- `arguments_hash`: `hash_prompt` of the full raw arguments string.
- `arguments_preview`: the raw arguments string, URL-redacted (below), then
  cut to 500 -- `audit_logger`'s preview length, imported rather than copied.
- `classifications`: a JSON array of `{rule, kind, detail}`, every
  classification in order; `kind` is the operation's kind, or null.
- `write_id`: one batch hex per `record()` call, plus `:<index>` (0-based, input
  order). The key a replay of a landed batch is recognised by, so it lands
  exactly once (PRD-018 D4). NULL only for a row built without one.

Redaction (STORY-012/015 orchestrator decisions). An `http` target is the whole
URL, and a query string can carry a token. So the stored target of an `http`
operation keeps its keys and replaces every query and fragment value with
`***`, and any userinfo (`user:token@`) becomes `***`. `arguments_preview` must
not leak what `target_preview` hides, so every `http://` / `https://` substring
inside it -- a `webfetch` URL, a shell `curl` target, a JSON-escaped one -- gets
the same treatment, and so does a non-`http` target (a whole `shell` command).
Redaction runs **before** truncation, so a cut never separates a key from its
`***`. Apart from URLs the preview stays raw, as T10 accepts: the hash is over
the unredacted string, so identical calls still group.

No catch. A storage failure surfaces as `app.db.errors.StorageError` (or
`IntegrityError`) from `_session()`. What the live path does is PRD-017 D8's
decision, made in the pipeline, not here: it turns the failure into
`ActionAuditError` and fails closed.
"""

import json
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, Sequence

from app.db.database import insert_action_decisions
from app.db.models import ActionDecisionRow

# Section 6.12: the action audit reuses audit_logger's preview convention -- one
# 500, not a copy that can drift. Underscore names by convention only.
from app.services.audit_logger import (
    _PREVIEW_LENGTH,
    _TIMESTAMP_FORMAT,
    _new_write_id,
)
from app.services.duplicate_checker import hash_prompt

if TYPE_CHECKING:
    from app.services.action_policy import ActionDecision
    from app.services.identity import Identity

#: The repo's redaction marker (`app/db/database.py`'s `_REDACTED`).
_REDACTED = "***"

#: An `http://` or `https://` URL inside free text. It ends at whitespace, a
#: quote, `<`, `>`, a backtick or a backslash -- except `\/`, a JSON-escaped
#: slash, which stays inside, so `https:\/\/x\/a?token=t` is one URL. A plain
#: scan: it never raises and needs the URL to parse no more than the target does.
_URL_IN_TEXT = re.compile(r"https?:(?:\\?/){2}(?:\\/|[^\s\"'<>\\`])*", re.IGNORECASE)

#: Up to and including the first `//` (or JSON-escaped `\/\/`), then the
#: authority, which runs to the next `/`.
_AUTHORITY = re.compile(r"(?s)(.*?(?:\\?/){2})([^/]*)(.*)")


def _redact_pairs(text: str) -> str:
    """Each `&`-separated item: `k=v` -> `k=***`, `k=` stays, a bare item -> `***`.

    A bare item is a value (`?AKIA...`, `#token`), so redacting it fails safe.
    An empty item (`&&`) stays empty.
    """
    items = []
    for item in text.split("&"):
        if not item:
            items.append(item)
            continue
        key, eq, value = item.partition("=")
        if not eq:
            items.append(_REDACTED)
        elif value:
            items.append(f"{key}={_REDACTED}")
        else:
            items.append(item)
    return "&".join(items)


def _redact_url(url: str) -> str:
    """`url` with query and fragment values and any userinfo redacted.

    A string split, not `urlsplit`: total and never raising, so a URL that
    `urlsplit` rejects (`net.unparsed`, e.g. `http://[bad/x?k=v`) is still
    redacted. The boundaries are `urlsplit`'s: the first `#`, then the first
    `?` before it. An empty query or fragment stays empty.
    """
    head, hash_sep, fragment = url.partition("#")
    base, q_sep, query = head.partition("?")
    match = _AUTHORITY.fullmatch(base)
    if match is not None:
        lead, authority, rest = match.groups()
        userinfo, at, host = authority.rpartition("@")
        if at:
            base = f"{lead}{_REDACTED}@{host}{rest}"
    return base + q_sep + _redact_pairs(query) + hash_sep + _redact_pairs(fragment)


def _redact_urls_in(text: str) -> str:
    """Every `http(s)://` URL inside `text` through `_redact_url`; the rest raw."""
    return _URL_IN_TEXT.sub(lambda m: _redact_url(m.group(0)), text)


def _target_preview(d: "ActionDecision") -> Optional[str]:
    """The reported operation's target, redacted, then cut to 500; None without one."""
    if d.operation is None:
        return None
    target = d.operation.target
    redacted = _redact_url(target) if d.operation.kind == "http" else _redact_urls_in(target)
    return redacted[:_PREVIEW_LENGTH]


def _classifications_json(d: "ActionDecision") -> str:
    """Every classification as `{rule, kind, detail}`, in order (Section 6.10)."""
    return json.dumps(
        [
            {
                "rule": c.rule,
                "kind": c.operation.kind if c.operation is not None else None,
                "detail": c.detail,
            }
            for c in d.classifications
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _row_of(
    d: "ActionDecision",
    identity: "Identity",
    timestamp: str,
    audit_id: Optional[int],
    session_id: Optional[str],
    write_id: Optional[str] = None,
) -> ActionDecisionRow:
    return ActionDecisionRow(
        timestamp=timestamp,
        audit_id=audit_id,
        session_id=session_id,
        user_id=identity.user_id,
        role=identity.role,
        tool_call_id=d.tool_call_id,
        tool_name=d.tool_name,
        operation_kind=d.operation.kind if d.operation is not None else None,
        target_preview=_target_preview(d),
        arguments_hash=hash_prompt(d.arguments),
        arguments_preview=_redact_urls_in(d.arguments)[:_PREVIEW_LENGTH],
        decision=d.decision,
        rule=d.rule,
        reason=d.reason,
        granted_by=d.granted_by,
        classifications=_classifications_json(d),
        policy_digest=d.policy_digest,
        write_id=write_id,
    )


def record(
    decisions: Sequence["ActionDecision"],
    identity: "Identity",
    audit_id: Optional[int] = None,
    session_id: Optional[str] = None,
) -> list[int]:
    """Store one row per decision; return the new ids, in input order (Section 10).

    One transaction (`insert_action_decisions`): every row of the batch lands,
    or none does. All rows share one UTC timestamp. `record([])` returns `[]`
    and writes nothing.

    PRD-018 D4: one batch hex is minted per call, before the first attempt, and
    row *i* is keyed `"<batch>:<i>"` (0-based, input order). Every row carries a
    key, so the unit is retried from row 1 on any infrastructure failure and a
    replay of a landed batch lands each row once.
    """
    if not decisions:
        return []
    timestamp = datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)
    batch = _new_write_id()
    rows = [
        _row_of(d, identity, timestamp, audit_id, session_id, f"{batch}:{index}")
        for index, d in enumerate(decisions)
    ]
    return insert_action_decisions(rows)
