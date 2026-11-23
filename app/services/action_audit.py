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
- `write_id`: `<audit write_id>:<index>` (0-based, input order) when `record()`
  is given the success row's `AuditRef`; a fresh batch hex plus `:<index>` for a
  direct call with no ref. The key a replay of a landed batch is recognised by,
  so it lands exactly once (PRD-018 D4, STORY-010). NULL only for a row built
  without one.

A gateway row (PRD-023 D21, STORY-008; `record(..., mcp=McpRecord(...))`) adds:

- `surface='mcp'`, `mcp_server`, `mcp_config_digest`, `arguments_canonical_hash`,
  `linked_decision_id`: from the `McpRecord`.
- `skills`: a compact JSON array of `"name@version"` strings.
- `tool_call_id`: `"mcp:" + str(jsonrpc_id)`; `session_id` is NULL; `audit_id` is
  the `McpRecord`'s (NULL unless correlated to a `/v1` request).
- `outcome`, `duration_ms`, `result_bytes`, `result_hash`, `result_flags`: NULL
  at the pre-forward write; `record_outcome` fills them after the call. Results
  are never stored, only a hash, a size and flag names (T14).

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

One catch (PRD-018 F7, D13, O8). Given an `AuditRef` whose row committed, a
`StorageUnavailableError` on the decisions write is journaled as a
decisions-only entry (`audit_id` known, `write_id` the row's own) and `record`
returns `[]`; `AuditUnavailableError` from a failed append propagates. Any other
`StorageError` (or `IntegrityError`) surfaces untouched. What the live path does
with a failure is PRD-017 D8's decision, made in the pipeline: it turns it into
`ActionAuditError` and fails closed.
"""

import dataclasses
import hashlib
import json
import re
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional, Sequence, Union

from app.db import audit_journal
from app.db.database import insert_action_decisions, update_action_outcome
from app.db.errors import StorageUnavailableError
from app.db.models import MCP_OUTCOME_VALUES, ActionDecisionRow

# Section 6.12: the action audit reuses audit_logger's preview convention -- one
# 500, not a copy that can drift. Underscore names by convention only.
from app.services.audit_logger import (
    AuditRef,
    _PREVIEW_LENGTH,
    _TIMESTAMP_FORMAT,
    _new_write_id,
)
from app.services.duplicate_checker import hash_prompt

if TYPE_CHECKING:
    from app.services.action_policy import ActionDecision
    from app.services.identity import Identity

logger = logging.getLogger(__name__)

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


def decision_rows(
    decisions: Sequence["ActionDecision"],
    identity: "Identity",
    write_id: str,
    audit_id: Optional[int] = None,
    session_id: Optional[str] = None,
) -> list[ActionDecisionRow]:
    """One row per decision, keyed `"<write_id>:<i>"`, sharing one UTC timestamp.

    PRD-018 D13. The one builder both paths use: `record` for the rows it
    writes, and step 8's `log_query(journal_decisions=...)` for the rows that
    ride in a journaled audit entry, so the two are identical.
    """
    timestamp = datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)
    return [
        _row_of(d, identity, timestamp, audit_id, session_id, f"{write_id}:{index}")
        for index, d in enumerate(decisions)
    ]


def canonical_json(obj: Any) -> str:
    """The canonical JSON text of `obj` (PRD-023 Section 6.3): sorted keys, no
    whitespace, non-ASCII kept. What `arguments_canonical_hash` is taken over, so
    the same arguments hash the same however the caller ordered the keys."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def arguments_canonical_hash(arguments: Any) -> str:
    """sha256 hex of `canonical_json(arguments)` as UTF-8 (PRD-023 D21)."""
    return hashlib.sha256(canonical_json(arguments).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class McpRecord:
    """The gateway-only facts of one `record(..., mcp=)` row (PRD-023 D21).

    `surface` is `"mcp"` and nothing else for now; anything else raises
    `ValueError`. `audit_id` is the correlated `/v1` request's audit row, or
    None. `jsonrpc_id` becomes `tool_call_id` as `"mcp:<id>"`.
    """

    surface: str
    #: None when the called name has no configured-server prefix (PRD-023 STORY-013).
    mcp_server: Optional[str]
    skills: tuple[str, ...]
    arguments_canonical_hash: str
    linked_decision_id: Optional[int]
    mcp_config_digest: str
    jsonrpc_id: Union[str, int]
    audit_id: Optional[int] = None

    def __post_init__(self) -> None:
        if self.surface != "mcp":
            raise ValueError(
                f"McpRecord.surface must be 'mcp', got {self.surface!r} (PRD-023 D21)"
            )


def record(
    decisions: Sequence["ActionDecision"],
    identity: "Identity",
    audit_ref: Optional[AuditRef] = None,
    session_id: Optional[str] = None,
    *,
    mcp: Optional[McpRecord] = None,
) -> list[int]:
    """Store one row per decision; return the new ids, in input order (Section 10).

    One transaction (`insert_action_decisions`): every row of the batch lands,
    or none does. All rows share one UTC timestamp. `record([])` returns `[]`
    and writes nothing.

    PRD-018 D4, F7: with an `audit_ref`, row *i* is keyed
    `"<audit_ref.write_id>:<i>"` and linked to `audit_ref.audit_id`. With none (a
    direct call) a fresh batch hex is minted and `audit_id` is NULL. Every row
    carries a key, so the unit is retried from row 1 on any infrastructure
    failure and a replay of a landed batch lands each row once.

    O8 rule (PRD-018 O8, D13): the journal satisfies "recorded" only for
    PRD-017's post-response release -- step 8, with the ref `log_query`
    returned. If that write raises `StorageUnavailableError`, the decisions are
    journaled alone (`audit_id` known) and `[]` is returned. A pre-execution
    decision write (PRD-023's MCP pre-forward write, PRD-023 T9) must call
    without a ref, or `database.insert_action_decisions` directly: that path
    commits or raises and never journals.

    A journaled ref (`audit_id is None`) is a caller bug: its decisions already
    went into the row's journal entry (D13), so the pipeline does not call
    `record` and this raises `ValueError` (orchestrator ruling R3).

    **`mcp=` (PRD-023 D9, T9, D21): the gateway's pre-forward write.** Exactly
    one decision, and no `audit_ref` or `session_id` (`ValueError` otherwise).
    The row is keyed with a fresh `write_id`, carries the `McpRecord`'s fields,
    and is written with no try/except and no journal: any `StorageError`
    propagates, so the caller forwards nothing unless this returned.
    """
    if mcp is not None:
        if audit_ref is not None or session_id is not None:
            raise ValueError(
                "record(mcp=...) takes no audit_ref or session_id: a gateway row "
                "is written before the forward and never journaled (PRD-023 T9)"
            )
        if len(decisions) != 1:
            raise ValueError(
                f"record(mcp=...) takes exactly one decision, got {len(decisions)}"
            )
        base = decision_rows(decisions, identity, _new_write_id(), mcp.audit_id, None)
        rows = [
            dataclasses.replace(
                row,
                tool_call_id=f"mcp:{mcp.jsonrpc_id}",
                session_id=None,
                surface=mcp.surface,
                mcp_server=mcp.mcp_server,
                skills=json.dumps(list(mcp.skills), separators=(",", ":")),
                arguments_canonical_hash=mcp.arguments_canonical_hash,
                linked_decision_id=mcp.linked_decision_id,
                mcp_config_digest=mcp.mcp_config_digest,
            )
            for row in base
        ]
        return insert_action_decisions(rows)
    if audit_ref is not None and audit_ref.audit_id is None:
        raise ValueError(
            "record() was given a journaled AuditRef (audit_id None): its "
            "decisions already ride in the row's journal entry (PRD-018 D13)"
        )
    if not decisions:
        return []
    if audit_ref is None:
        rows = decision_rows(decisions, identity, _new_write_id(), None, session_id)
        return insert_action_decisions(rows)
    rows = decision_rows(
        decisions, identity, audit_ref.write_id, audit_ref.audit_id, session_id
    )
    try:
        return insert_action_decisions(rows)
    except StorageUnavailableError:
        # R6: the entry's write_id is the audit row's own. It was never
        # journaled (the row committed), so it cannot collide with a pending
        # entry. AuditUnavailableError from a failed append propagates.
        audit_journal.append(
            None, rows, audit_id=audit_ref.audit_id, write_id=audit_ref.write_id
        )
        logger.warning(
            "action decisions journaled: user_id=%s audit_id=%s write_id=%s decisions=%d",
            identity.user_id,
            audit_ref.audit_id,
            audit_ref.write_id,
            len(rows),
        )
        return []


def record_outcome(
    row_id: int,
    outcome: str,
    duration_ms: Optional[int],
    result_bytes: Optional[int],
    result_hash: Optional[str],
    result_flags: Sequence[str],
    *,
    user_id: str,
) -> None:
    """Fill a gateway row's outcome columns after the call (PRD-023 D21, T14).

    Best effort: never raises into the response path. An `outcome` outside
    `MCP_OUTCOME_VALUES` is logged at ERROR and not written; a failed UPDATE is
    logged at ERROR with the exception class only (its message could carry
    anything). `result_flags` is flag names only, stored as a JSON array; there
    is no parameter for result content. `user_id` is keyword-only because after
    a failed UPDATE nothing can be read back to name the user.
    """
    if outcome not in MCP_OUTCOME_VALUES:
        logger.error(
            "mcp outcome not recorded, unknown outcome: user_id=%s row_id=%s outcome=%r",
            user_id,
            row_id,
            outcome,
        )
        return
    try:
        update_action_outcome(
            row_id,
            outcome,
            duration_ms,
            result_bytes,
            result_hash,
            json.dumps(list(result_flags), separators=(",", ":")),
        )
    except Exception as exc:
        logger.error(
            "mcp outcome not recorded: user_id=%s row_id=%s: %s",
            user_id,
            row_id,
            type(exc).__name__,
        )
