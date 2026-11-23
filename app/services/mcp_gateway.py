"""The gateway's visible catalogue: what `tools/list` returns (PRD-023 Section 6.5, F5, D6, D7, D12).

`visible_catalogue(identity)` starts from `mcp_config.visible_tools(identity)`
(the union of the held skills' tools), fetches each server's cached upstream
list through `mcp_upstream.list_tools` (the only upstream call here; no second
cache), keeps the tools that are both held and listed, injection-inspects them
and returns the northbound tool dicts plus the `callable` map. STORY-013's call
path reuses `callable`: a withheld or unlisted tool is not callable (-32602).

Inspection (D12, T3, O6). D12 names one list, `injection`. It runs over the
tool's `description`, its `title`, and every string value under a `description`
key anywhere inside `inputSchema` (a nested property, `items`, `oneOf`, ...).
Property names, `default` and `enum` values are not inspected. A tool is
withheld, with a WARNING naming the server, the tool and the matched list
names (never the text, a pattern or a phrase), on a `block` hit, on a `flag`
hit, or when any text is longer than `PATTERN_MAX_SCAN_CHARACTERS` (the text
past the ceiling would go unscanned, so it fails closed). If a deployment's
pattern file defines no `injection` list, the built-in one is used.

Nothing is written to the database (O4): `tools/list` is not an action. The
gateway never raises for an unreachable server; that server contributes no
tool and one WARNING with the exception class name only (T16).

`call(identity, params, request_id)` is the `tools/call` path (PRD-023 Section
6.3, M3-M9, D8, D9, D13-D15). In order: M3 the params shape (a fault is -32602
and no row), M4 `usage_limits.admit(charges_budget=False)` when
`USAGE_LIMITS_ENABLED` (refused: `UsageRefused`, no row, nothing forwarded), M5
`visible_catalogue(identity).callable`, M6 `action_policy.evaluate(...,
surface=McpSurface)`, M7 the decision row, written BEFORE any forward through
`action_audit.record(..., mcp=)` with no `audit_ref` (T9: it commits or raises,
never journals), M8 the deny note or `mcp_upstream.call_tool`, M9
`record_outcome`, best effort. A call that is not callable (hidden, unlisted,
withheld, unconfigured, nonexistent) is one recorded -32602 with one text (T6).
Nothing is forwarded twice (T10). Results are not stored: size, hash and flags
only. Texts sent to the agent name the tool and the call id, never a URL, a
header or an env name (T16).

This module imports no `mcp` package (T17); only `app/services/mcp_upstream.py`
does.
"""

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from types import MappingProxyType, SimpleNamespace
from typing import Any, Mapping, Optional

from app.config import settings
from app.services import (
    action_audit,
    action_policy,
    mcp_config,
    mcp_upstream,
    pattern_config,
    pattern_detector,
    pipeline_executor,
    usage_limits,
)
from app.services.action_adapters import ToolCall
from app.services.identity import Identity
from app.services.tool_release import DENIAL_NOTE_TEMPLATE, NOTE_FIELD_CAP

logger = logging.getLogger(__name__)

#: JSON-RPC codes used by `call` (the router's `schemas` module is not importable from here).
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603

#: One text for every name that is not callable (T6): hidden, unlisted, withheld,
#: nonexistent and unconfigured are indistinguishable to the agent.
UNKNOWN_TOOL_MESSAGE = "Unknown tool"
INVALID_NAME_MESSAGE = "Invalid params: name must be a non-empty string"
INVALID_ARGUMENTS_MESSAGE = "Invalid params: arguments must be an object"
RECORD_FAILED_MESSAGE = "decision could not be recorded"
USAGE_UNCHECKED_MESSAGE = "usage could not be checked"
#: Harness-made `isError` texts (PRD-023 Section 10). The call may have run.
TIMEOUT_TEXT = "[harness] {name} ({id}) timed out after {n}s; the call may have run"
UPSTREAM_ERROR_TEXT = "[harness] {name} ({id}) failed on server {server}; the call may have run"

_NAME_CAP = 256

#: Module attribute so tests drive the once-per-period INFO expiry with an injected clock.
_now = time.monotonic

#: (kind, server, tool) -> expiry, for the INFO lines logged once per cache period.
_unlisted_logged: dict[tuple, float] = {}

_MAX_SCHEMA_DEPTH = 64
_INSPECTED_ROLE = "tool"


@dataclass(frozen=True)
class Catalogue:
    """What one identity may see and call (PRD-023 Section 6.5).

    `tools` is sorted by prefixed name. `callable` is server id -> the bare
    tool names actually emitted (held, listed and not withheld); a server with
    none is absent.
    """

    tools: tuple[dict, ...] = ()
    callable: Mapping[str, frozenset[str]] = field(default_factory=lambda: MappingProxyType({}))


def _log_once(key: tuple, message: str, *args: Any) -> None:
    """INFO once per `MCP_TOOLS_CACHE_SECONDS` for `key`; `0` logs every time."""
    ttl = settings.MCP_TOOLS_CACHE_SECONDS
    now = _now()
    for stale in [k for k, expiry in _unlisted_logged.items() if expiry <= now]:
        del _unlisted_logged[stale]
    if ttl > 0:
        if key in _unlisted_logged:
            return
        _unlisted_logged[key] = now + ttl
    logger.info(message, *args)


def _schema_descriptions(schema: Any, depth: int = 0) -> list[str]:
    """Every string value of a `description` key anywhere inside `schema`."""
    found: list[str] = []
    if depth > _MAX_SCHEMA_DEPTH:
        return found
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "description" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_schema_descriptions(value, depth + 1))
    elif isinstance(schema, list):
        for item in schema:
            found.extend(_schema_descriptions(item, depth + 1))
    return found


def _injection_profile() -> pattern_config.Profile:
    lists = pattern_config.get_policy().lists
    injection = lists.get("injection") or pattern_config.BUILT_IN_POLICY.lists["injection"]
    return pattern_config.Profile(
        name="mcp-catalogue", lists=(injection,), roles={_INSPECTED_ROLE: "block"}
    )


def _withheld_by(tool: mcp_upstream.UpstreamTool) -> tuple[str, ...]:
    """The list names that withhold `tool`; empty means it is clean."""
    texts = [tool.description]
    if tool.title:
        texts.append(tool.title)
    texts.extend(_schema_descriptions(tool.input_schema))
    turns = [SimpleNamespace(role=_INSPECTED_ROLE, content=t) for t in texts if t]
    result = pattern_detector.inspect(
        turns, _injection_profile(), max_scan_characters=settings.PATTERN_MAX_SCAN_CHARACTERS
    )
    names: list[str] = []
    if result.block is not None:
        names.append(result.block.list_name)
    names.extend(h.list_name for h in result.flags)
    if result.truncated and not names:
        names.append("scan_ceiling")
    return tuple(dict.fromkeys(names))


def _northbound(server: str, tool: mcp_upstream.UpstreamTool) -> dict:
    """One tool as `tools/list` shows it. `inputSchema` is verbatim (`x-mcp-header`
    survives). `icons` and `_meta` are dropped (STORY-002 safe default)."""
    entry: dict = {
        "name": f"{server}__{tool.name}",
        "description": tool.description,
        "inputSchema": tool.input_schema,
    }
    if tool.title is not None:
        entry["title"] = tool.title
    if tool.output_schema is not None:
        entry["outputSchema"] = tool.output_schema
    if tool.annotations is not None:
        entry["annotations"] = tool.annotations
    return entry


async def visible_catalogue(identity: Identity) -> Catalogue:
    """The tools `identity` may see and call, prefixed and inspected (D6, D7, D12)."""
    visible = mcp_config.visible_tools(identity)
    if not visible:
        return Catalogue()
    server_ids = sorted(visible)
    listed = await asyncio.gather(
        *(mcp_upstream.list_tools(sid, identity.user_id) for sid in server_ids),
        return_exceptions=True,
    )
    entries: list[dict] = []
    callable_by_server: dict[str, frozenset[str]] = {}
    for sid, upstream in zip(server_ids, listed):
        if isinstance(upstream, BaseException) and not isinstance(upstream, Exception):
            raise upstream  # CancelledError and friends are never swallowed
        if isinstance(upstream, Exception):
            # The class name only: an exception's text may carry a URL or a header (T16).
            logger.warning(
                "mcp tools/list: server=%s failed (%s)", sid, type(upstream).__name__
            )
            continue
        by_name = {t.name: t for t in upstream}
        emitted: set[str] = set()
        for bare in sorted(visible[sid]):
            tool = by_name.get(bare)
            if tool is None:
                _log_once(
                    ("unlisted", sid, bare),
                    "mcp tools/list: server=%s tool=%s is in a held skill but not listed upstream",
                    sid, bare,
                )
                continue
            matched = _withheld_by(tool)
            if matched:
                logger.warning(
                    "mcp tools/list: withheld server=%s tool=%s lists=%s",
                    sid, bare, ",".join(matched),
                )
                continue
            if tool.input_schema.get("type") != "object":
                _log_once(
                    ("schema", sid, bare),
                    "mcp tools/list: server=%s tool=%s inputSchema is not type=object; passed through",
                    sid, bare,
                )
            entries.append(_northbound(sid, tool))
            emitted.add(bare)
        if emitted:
            callable_by_server[sid] = frozenset(emitted)
    entries.sort(key=lambda e: e["name"])
    return Catalogue(tools=tuple(entries), callable=MappingProxyType(callable_by_server))


# --- tools/call (PRD-023 Section 6.3, M3-M9) -----------------------------------


class GatewayRpcError(Exception):
    """A JSON-RPC error the router answers as HTTP 200 (`code`, `message`)."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class UsageRefused(Exception):
    """M4: the usage limit refused the call. The router answers 429 with `Retry-After`."""

    def __init__(self, retry_after_seconds: int, limit: str):
        super().__init__(f"usage limit reached: {limit}")
        self.retry_after_seconds = retry_after_seconds
        self.limit = limit


def result_digest(result: Mapping[str, Any]) -> tuple[int, str]:
    """`(byte length, sha256 hex)` of `result`'s canonical JSON: what the row keeps
    instead of the result (T14). STORY-014 digests what it finally returns."""
    encoded = action_audit.canonical_json(result).encode("utf-8")
    return len(encoded), hashlib.sha256(encoded).hexdigest()


def _correlate(
    identity: Identity, server: Optional[str], tool: Optional[str], arguments_hash: str
) -> tuple[Optional[int], Optional[int]]:
    """`(audit_id, linked_decision_id)` of the `/v1` call this one continues.

    STORY-016 replaces the body (alias resolution and the correlation claim);
    until then no call is correlated."""
    return None, None


def _tool_result(content: list, is_error: bool, structured: Optional[dict] = None) -> dict:
    result: dict = {"content": content, "isError": is_error}
    if structured is not None:
        result["structuredContent"] = structured
    return result


def _harness_error(text: str) -> dict:
    return _tool_result([{"type": "text", "text": text}], True)


def _held_skill_labels(identity: Identity, prefixed: str) -> tuple[str, ...]:
    return tuple(
        f"{s.id}@{s.version}" for s in mcp_config.held_skills(identity) if prefixed in s.tools
    )


def _parse_params(params: Mapping[str, Any]) -> tuple[str, dict, str]:
    """M3: `(name, arguments, canonical arguments text)`. A fault is -32602, no row."""
    name = params.get("name")
    if not isinstance(name, str) or not name:
        raise GatewayRpcError(_INVALID_PARAMS, INVALID_NAME_MESSAGE)
    arguments = params["arguments"] if "arguments" in params else {}
    if not isinstance(arguments, dict):
        raise GatewayRpcError(_INVALID_PARAMS, INVALID_ARGUMENTS_MESSAGE)
    try:
        canonical = action_audit.canonical_json(arguments)
    except (ValueError, TypeError, RecursionError):
        raise GatewayRpcError(_INVALID_PARAMS, INVALID_ARGUMENTS_MESSAGE)
    return name, arguments, canonical


async def _admit(identity: Identity) -> None:
    """M4. Counts the attempt; `charges_budget=False` (a tool call spends no model tokens)."""
    if not settings.USAGE_LIMITS_ENABLED:
        return
    try:
        admission = await pipeline_executor.run_in_pipeline(usage_limits.admit, identity, False)
    except usage_limits.UsageLimitError:
        raise GatewayRpcError(_INTERNAL_ERROR, USAGE_UNCHECKED_MESSAGE)
    if not admission.admitted:
        refusal = admission.refusal
        now = datetime.now(timezone.utc)
        raise UsageRefused(usage_limits.retry_after_seconds(refusal, now), refusal.limit)


async def _write_outcome(
    identity: Identity, row_id: int, outcome: str, duration_ms: int, result: Mapping[str, Any]
) -> None:
    """M9: best effort. Never raises into the response path."""
    try:
        size, digest = result_digest(result)
        await pipeline_executor.run_in_pipeline(
            action_audit.record_outcome,
            row_id, outcome, duration_ms, size, digest, (),
            user_id=identity.user_id,
        )
    except Exception as exc:
        logger.error(
            "mcp outcome not recorded: user_id=%s row_id=%s: %s",
            identity.user_id, row_id, type(exc).__name__,
        )


async def call(identity: Identity, params: Mapping[str, Any], request_id: Any) -> dict:
    """One `tools/call` (M3-M9). Returns the MCP result dict; raises `GatewayRpcError`
    or `UsageRefused`. Nothing is forwarded until the decision row has committed."""
    name, arguments, canonical = _parse_params(params)
    await _admit(identity)

    catalogue = await visible_catalogue(identity)
    try:
        server, tool = mcp_config.split_tool(name)
    except ValueError:
        server, tool = None, None
    if server is not None:
        surface = action_policy.McpSurface(server, catalogue.callable.get(server, frozenset()))
        engine_call = ToolCall(str(request_id), tool, canonical)
    else:
        surface = action_policy.McpSurface("", frozenset())
        engine_call = ToolCall(str(request_id), name[:_NAME_CAP], canonical)
    decision = action_policy.evaluate(engine_call, identity, surface=surface)

    arguments_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    audit_id, linked = _correlate(identity, server, tool, arguments_hash)
    record = action_audit.McpRecord(
        surface="mcp",
        mcp_server=server,
        skills=_held_skill_labels(identity, name) if server is not None else (),
        arguments_canonical_hash=arguments_hash,
        linked_decision_id=linked,
        mcp_config_digest=mcp_config.mcp_config_digest(),
        jsonrpc_id=request_id,
        audit_id=audit_id,
    )
    try:
        row_ids = await pipeline_executor.run_in_pipeline(
            action_audit.record, [decision], identity, mcp=record
        )
        if len(row_ids) != 1:
            raise RuntimeError("unexpected row count")
    except Exception as exc:
        # Class name only (T16). Nothing was forwarded: the row is the evidence (T9).
        logger.warning(
            "mcp tools/call: decision not recorded: user_id=%s server=%s (%s)",
            identity.user_id, server, type(exc).__name__,
        )
        raise GatewayRpcError(_INTERNAL_ERROR, RECORD_FAILED_MESSAGE)
    row_id = row_ids[0]

    logger.info(
        "mcp tools/call: user=%s server=%s tool=%s decision=%s rule=%s",
        identity.user_id, server, tool, decision.decision, decision.rule,
    )
    if decision.rule == "tool.not_in_skill":
        raise GatewayRpcError(_INVALID_PARAMS, UNKNOWN_TOOL_MESSAGE)
    call_id = str(request_id)
    if decision.decision == "deny":
        return _harness_error(
            DENIAL_NOTE_TEMPLATE.format(
                name=name[:NOTE_FIELD_CAP], id=call_id[:NOTE_FIELD_CAP], reason=decision.reason
            )
        )

    started = time.monotonic()
    try:
        outcome = await mcp_upstream.call_tool(server, identity.user_id, tool, arguments)
    except Exception as exc:  # call_tool never raises for an upstream failure; stay safe
        outcome = mcp_upstream.CallOutcome("upstream_error", detail=type(exc).__name__)
    duration_ms = int((time.monotonic() - started) * 1000)

    if outcome.outcome == "timeout":
        recorded = "timeout"
        seconds = mcp_config.get_config().servers[server].timeout_seconds
        result = _harness_error(
            TIMEOUT_TEXT.format(name=name[:NOTE_FIELD_CAP], id=call_id[:NOTE_FIELD_CAP], n=seconds)
        )
    elif outcome.outcome == "upstream_error":
        recorded = "upstream_error"
        result = _harness_error(
            UPSTREAM_ERROR_TEXT.format(
                name=name[:NOTE_FIELD_CAP], id=call_id[:NOTE_FIELD_CAP], server=server
            )
        )
    else:
        failed = outcome.outcome == "error" or outcome.is_error
        recorded = "tool_error" if failed else "ok"
        result = _tool_result(outcome.content, failed, outcome.structured)
    # `detail` is credential-safe by contract (mcp_upstream); it goes to the log, never the response.
    logger.info(
        "mcp tools/call: user=%s server=%s tool=%s outcome=%s duration_ms=%d detail=%s",
        identity.user_id, server, tool, recorded, duration_ms, outcome.detail,
    )
    await _write_outcome(identity, row_id, recorded, duration_ms, result)
    return result
